# CLAUDE.md — China Logistics Pulse

## 项目概述

本项目抓取中国交通运输部"物流保通保畅"专题下的周度通报数据，结构化存储到 SQLite，并生成可视化图表。数据涵盖铁路货运量、高速公路货车通行量、港口吞吐量、集装箱吞吐量、民航航班、邮政快递揽收/投递量等指标。

英文项目名：**China Logistics Pulse**

## 目录结构

```
china-logistics-pulse/
├── CLAUDE.md                # 本文件，给 Claude Code 的指引
├── README.md                # GitHub 项目首页（含动态生成内容）
├── requirements.txt         # Python 依赖
├── .github/
│   └── workflows/
│       └── weekly_update.yml  # GitHub Actions 每周三自动更新
├── scripts/
│   ├── 01_init_db.py          # 初始化 SQLite 数据库
│   ├── 02_fetch_index.py      # 抓取索引页，获取所有通报链接
│   ├── 03_parse_report.py     # 解析单篇通报 HTML，提取结构化数据
│   ├── 04_backfill.py         # 批量回填历史数据（组合 02+03）
│   ├── 05_generate_charts.py  # 生成可视化图表
│   ├── 06_generate_readme.py  # 动态生成 README.md
│   ├── update.py              # 一键增量更新（02→03→05→06 的流水线）
│   └── utils.py               # 公共工具函数
├── data/
│   ├── logistics.db           # 主数据库（结构化指标数据）
│   └── links.db               # 链接数据库（索引页抓取记录）
├── charts/                    # 生成的图表 PNG
│   ├── rail_freight_yoy.png
│   ├── highway_trucks_yoy.png
│   ├── port_cargo_yoy.png
│   ├── container_yoy.png
│   ├── aviation_yoy.png
│   ├── express_pickup_yoy.png
│   ├── express_delivery_yoy.png
│   └── ytd_growth_comparison.png
└── examples/                  # 范例 HTML 文件（供开发参考）
    ├── index.html             # 索引页范例
    └── report.html            # 单篇通报范例
```

## 数据源

### 索引页 URL 规律

- 第一页: `https://www.mot.gov.cn/zhuanti/wuliubtbc/qingkuangtongbao_wuliu/index.html`
- 第二页: `https://www.mot.gov.cn/zhuanti/wuliubtbc/qingkuangtongbao_wuliu/index_1.html`
- 第三页: `https://www.mot.gov.cn/zhuanti/wuliubtbc/qingkuangtongbao_wuliu/index_2.html`
- 以此类推: `index_{n}.html`，n 从 1 开始递增

翻页直到返回 404 或页面无有效链接为止。

### 通报页面

每篇通报的 URL 从索引页的链接列表中获取。通报标题格式示例：
```
X月X日—X月X日全国物流保通保畅运行情况
```

**重要**：年份信息不在标题中，需要从通报详情页获取（发布日期通常在页面中，格式如 `2026-03-10 09:30:12`）。解析时根据发布日期推断数据所属年份。注意跨年周的情况（12月底的周可能在1月初发布）。

### 数据格式

每期通报包含以下指标（部分指标可能在早期通报中不存在，需容错处理）：

| 指标 | 字段名 | 单位 | 示例正则 |
|------|--------|------|---------|
| 国家铁路货运量 | `rail_freight` | 万吨 | `国家铁路运输货物([\d.]+)万吨` |
| 高速公路货车通行量 | `highway_trucks` | 万辆 | `全国高速公路货车通行([\d.]+)万辆` |
| 港口货物吞吐量 | `port_cargo` | 万吨 | `监测港口完成货物吞吐量([\d.]+)万吨` |
| 集装箱吞吐量 | `container_throughput` | 万TEU | `完成集装箱吞吐量([\d.]+)万标箱` |
| 民航航班数 | `flights_total` | 万班 | `民航保障航班([\d.]+)万班` |
| 货运航班数 | `cargo_flights` | 班 | `其中货运航班(\d+)班` |
| 国际货运航班 | `intl_cargo_flights` | 班 | `国际货运航班(\d+)班` |
| 国内货运航班 | `domestic_cargo_flights` | 班 | `国内货运航班(\d+)班` |
| 快递揽收量 | `express_pickup` | 亿件 | `邮政快递揽收量约([\d.]+)亿件` |
| 快递投递量 | `express_delivery` | 亿件 | `投递量约([\d.]+)亿件` |

**环比数据**：每个指标后面通常跟随 `环比增长X.XX%` 或 `环比下降X.XX%`。可以一并提取存储，但对于分析而言意义不大（季节性强），主要用于交叉校验。

**注意事项**：
- 正则需要宽松匹配，因为不同期通报的措辞可能略有差异
- 早期通报的指标可能更少或格式不同，缺失字段存为 NULL
- 数字中可能有全角/半角混用的情况，预处理时统一转换

## 数据库设计

### links.db — 链接管理库

```sql
CREATE TABLE IF NOT EXISTS report_links (
    url TEXT PRIMARY KEY,              -- 通报详情页完整 URL
    title TEXT,                        -- 通报标题
    index_page TEXT,                   -- 来源索引页 URL
    discovered_at TEXT,                -- 首次发现时间 (ISO 8601)
    fetched INTEGER DEFAULT 0,         -- 是否已抓取解析: 0=未抓取, 1=已抓取, -1=抓取失败
    fetched_at TEXT                    -- 抓取时间
);
```

增量逻辑：`update.py` 运行时，先抓取索引页写入 links.db（新链接 fetched=0），然后只处理 `fetched=0` 的链接。

### logistics.db — 主数据库

```sql
CREATE TABLE IF NOT EXISTS weekly_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 时间标识
    week_start DATE NOT NULL,          -- 周一日期，如 '2026-03-02'
    week_end DATE NOT NULL,            -- 周日日期，如 '2026-03-08'
    iso_year INTEGER NOT NULL,         -- ISO 年份
    iso_week INTEGER NOT NULL,         -- ISO 周编号 (1-53)
    year INTEGER NOT NULL,             -- 自然年份（从发布日期推断）
    publish_date DATE,                 -- 通报发布日期
    
    -- 核心指标（单位见注释）
    rail_freight REAL,                 -- 铁路货运量（万吨）
    highway_trucks REAL,               -- 高速货车通行量（万辆）
    port_cargo REAL,                   -- 港口货物吞吐量（万吨）
    container_throughput REAL,         -- 集装箱吞吐量（万TEU/标箱）
    flights_total REAL,                -- 民航航班（万班）
    cargo_flights INTEGER,             -- 货运航班（班）
    intl_cargo_flights INTEGER,        -- 国际货运航班（班）
    domestic_cargo_flights INTEGER,    -- 国内货运航班（班）
    express_pickup REAL,               -- 快递揽收量（亿件）
    express_delivery REAL,             -- 快递投递量（亿件）
    
    -- 环比（原始通报中的百分比值，正数=增长，负数=下降）
    rail_freight_wow REAL,
    highway_trucks_wow REAL,
    port_cargo_wow REAL,
    container_throughput_wow REAL,
    flights_total_wow REAL,
    express_pickup_wow REAL,
    express_delivery_wow REAL,
    
    -- 元数据
    source_url TEXT,                   -- 通报原文 URL
    created_at TEXT DEFAULT (datetime('now')),
    
    UNIQUE(iso_year, iso_week)         -- 同一 ISO 周不重复
);
```

## 脚本详细说明

### 01_init_db.py
- 创建 `data/logistics.db` 和 `data/links.db`
- 执行上述建表 SQL
- 幂等操作，可重复运行

### 02_fetch_index.py
- 从索引页第一页开始，逐页抓取
- 解析页面中的通报链接和标题
- 插入 links.db，已存在的 URL 跳过（`INSERT OR IGNORE`）
- 翻页策略：从 `index.html` 开始，然后 `index_1.html`, `index_2.html`...直到页面无有效链接或 HTTP 错误
- 支持参数 `--max-pages N` 限制翻页数量（增量更新时用 `--max-pages 3` 即可）
- 打印新发现的链接数量

### 03_parse_report.py
- 接受参数：`--url URL` 解析单个通报，或 `--pending` 处理 links.db 中所有未抓取的
- 抓取通报详情页 HTML
- 从页面中提取发布日期（年份来源）
- 从标题中提取起止月日，结合年份计算 `week_start` 和 `week_end`
- 用正则从正文提取各项指标和环比
- 计算 ISO year 和 ISO week（基于 `week_start`）
- 写入 logistics.db（`INSERT OR REPLACE` 基于 iso_year + iso_week 唯一约束）
- 更新 links.db 中对应记录的 fetched 状态
- 对于解析失败的，设 `fetched=-1` 并打印警告

**日期解析注意事项**：
- 标题格式: `X月X日—X月X日`（注意中文破折号 `—` 或 `—`）
- 跨年情况: 如 `12月26日—1月1日`，需根据发布日期判断年份
- `week_start` 应始终是周一，如果通报起始日不是周一则需调整对齐（但根据观察通常是周一到周日）

### 04_backfill.py
- 首次运行的批量回填脚本
- 调用 02 抓取所有索引页（不限制 `--max-pages`）
- 调用 03 处理所有 pending 链接
- 支持 `--sleep N` 参数控制请求间隔（默认 1 秒，避免过于频繁）
- 打印进度和统计摘要

### 05_generate_charts.py
- 从 logistics.db 读取数据
- 使用 matplotlib 生成图表，保存到 `charts/` 目录
- 图表中文字体使用思源黑体或系统中文字体（脚本内需处理字体设置）
- **如果系统没有中文字体，使用英文标签即可**

需要生成的图表：

#### 1. 年度同期对比图（每个核心指标一张）
- X 轴: ISO 周编号 (W1-W53)
- Y 轴: 指标值
- 不同年份用不同颜色的线
- 至少展示近 3 年数据
- 图表命名: `{indicator}_yoy.png`（如 `rail_freight_yoy.png`）
- 文件列表: `rail_freight_yoy.png`, `highway_trucks_yoy.png`, `port_cargo_yoy.png`, `container_yoy.png`, `aviation_yoy.png`, `express_pickup_yoy.png`, `express_delivery_yoy.png`

#### 2. 年初至今（YTD）累计增速对比图
- 对每个核心指标，按 ISO 周累计计算 YTD 值
- 然后计算同比增速: `(YTD_current / YTD_previous - 1) * 100%`
- X 轴: ISO 周编号
- Y 轴: YTD 同比增速 (%)
- 不同指标用不同线/颜色
- 输出: `ytd_growth_comparison.png`
- 可以单独为每个指标也生成一张 YTD 图

#### 图表样式要求
- 风格简洁专业，参考 FT/Economist 风格
- 配色使用区分度高的调色板
- 添加网格线辅助阅读
- 图例清晰
- DPI 至少 150
- 标注最新数据点的值

### 06_generate_readme.py
- 读取 logistics.db 获取最新数据
- 动态生成 README.md 内容
- 嵌入最新的图表（使用相对路径引用 `charts/` 下的图片）
- 包含最近一期数据的摘要表格
- 包含数据更新时间戳
- 保留静态部分（项目介绍、结构说明等）不变，只替换动态部分
- 动态部分用 HTML 注释标记边界:
  ```
  <!-- DYNAMIC_START -->
  ...动态生成的内容...
  <!-- DYNAMIC_END -->
  ```

### update.py — 一键更新
```python
"""
增量更新流水线:
1. fetch_index (--max-pages 3): 获取最近几页索引，发现新通报链接
2. parse_report (--pending): 解析所有未抓取的通报
3. generate_charts: 重新生成所有图表
4. generate_readme: 更新 README.md
"""
```
- 依次调用上述步骤
- 使用 subprocess 或直接 import 调用
- 每步打印状态
- 支持 `--full` 参数执行完整回填（调用 04 代替 02+03）
- 支持 `--charts-only` 只重新生成图表和 README
- 支持 `--sleep N` 控制请求间隔

### utils.py — 公共函数
- `get_db_path(name)`: 返回 data 目录下的数据库路径
- `normalize_number(text)`: 全角数字转半角，移除空格
- `parse_date_range(title, publish_date)`: 从标题解析起止日期
- `calc_iso_week(date)`: 计算 ISO year 和 week
- `setup_chinese_font()`: 配置 matplotlib 中文字体（可选降级为英文）

## GitHub Actions

### .github/workflows/weekly_update.yml

```yaml
name: Weekly Update

on:
  schedule:
    - cron: '0 2 * * 3'  # 每周三 UTC 02:00（北京时间 10:00）
  workflow_dispatch:        # 支持手动触发

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run update
        run: python scripts/update.py --sleep 2
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ charts/ README.md
          git diff --cached --quiet || git commit -m "Weekly data update $(date +%Y-%m-%d)"
          git push
```

注意：由于数据源是中国政府网站，GitHub Actions 的网络环境通常可以访问（不像反过来）。如果遇到连接问题，可能需要配置代理。

## requirements.txt

```
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.1
matplotlib>=3.8
pandas>=2.1
```

## README.md 结构

README.md 应包含以下内容（静态+动态）：

### 静态部分
1. 项目名称和简介 badge（如 "Updated weekly"）
2. 项目说明：数据来源（交通运输部物流保通保畅专题）、更新频率、覆盖时间范围
3. 指标说明表格
4. 使用方法（如何运行 update.py、如何首次回填）
5. 项目结构
6. License

### 动态部分（`<!-- DYNAMIC_START -->` ... `<!-- DYNAMIC_END -->`）
1. 最后更新时间
2. 最近一期数据摘要表格（本周值 + 同比变化）
3. 核心图表嵌入（选取 2-3 张最有代表性的，如铁路、港口、快递）
4. 数据覆盖范围：从 YYYY-WXX 到 YYYY-WXX，共 N 周

## 编码规范

- Python 3.9+
- 使用 `pathlib` 处理路径
- 数据库操作使用 `with` 语句管理连接
- 所有网络请求设置合理的 timeout（10秒）和 User-Agent
- 日志使用 `print()` 即可，格式: `[步骤名] 消息`
- 所有脚本支持从项目根目录运行: `python scripts/01_init_db.py`
- 脚本内使用 `Path(__file__).resolve().parent.parent` 定位项目根目录

## 关键提醒

1. **年份来源**: 通报标题中没有年份，必须从详情页的发布日期获取
2. **编码**: 网页可能是 GBK/GB2312 编码，requests 获取后注意 `response.encoding`
3. **增量逻辑**: links.db 是增量更新的核心，通过 `fetched` 字段标记状态
4. **容错**: 早期通报格式可能不同，正则匹配失败时字段存 NULL，不要中断
5. **ISO Week**: 统一使用 `datetime.date.isocalendar()` 计算，不要自己算
6. **环比值**: 存储为带符号浮点数，"增长6.16%" → 6.16，"下降0.42%" → -0.42
7. **请求间隔**: 默认至少 1 秒间隔，避免对政府网站造成压力
8. **先看 examples/**: 开发前先查看 examples/ 目录下的 HTML 范例，了解实际页面结构后再写解析代码
