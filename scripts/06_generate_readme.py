"""
06_generate_readme.py — 动态生成 README.md 的动态部分

静态部分保留不变，动态部分在 <!-- DYNAMIC_START --> ... <!-- DYNAMIC_END --> 之间替换。
"""
import datetime
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_db_path

ROOT = Path(__file__).resolve().parent.parent
README_PATH = ROOT / "README.md"

STATIC_CONTENT = """\
# China Logistics Pulse 中国物流脉搏

[![Updated Weekly](https://img.shields.io/badge/Updated-Weekly-brightgreen)](https://github.com)
[![Data Source](https://img.shields.io/badge/Data-交通运输部-blue)](https://www.mot.gov.cn/zhuanti/wuliubtbc/qingkuangtongbao_wuliu/)

追踪中国物流运行的周度高频数据，数据来源：**交通运输部"物流保通保畅"专题**。

## 数据说明

| 指标 | 单位 | 说明 |
|------|------|------|
| 国家铁路货运量 | 万吨/周 | 国家铁路全周运输货物总量 |
| 高速公路货车通行量 | 万辆/周 | 全国高速公路货车通行总量 |
| 港口货物吞吐量 | 万吨/周 | 监测港口完成货物吞吐量 |
| 集装箱吞吐量 | 万TEU/周 | 监测港口完成集装箱吞吐量 |
| 民航航班数 | 万班/周 | 民航保障航班总数（含货运） |
| 快递揽收量 | 亿件/周 | 邮政快递揽收量 |
| 快递投递量 | 亿件/周 | 邮政快递投递量 |

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 首次运行（回填所有历史数据）
python scripts/01_init_db.py
python scripts/04_backfill.py --sleep 1

# 增量更新
python scripts/update.py

# 只重新生成图表
python scripts/update.py --charts-only
```

## 项目结构

```
china-logistics-pulse/
├── scripts/           # 数据抓取、解析、可视化脚本
├── data/              # SQLite 数据库
│   ├── logistics.db   # 结构化指标数据
│   └── links.db       # 链接管理数据库
├── charts/            # 生成的图表 PNG
└── examples/          # 参考 HTML 范例
```

## License

MIT

---

<!-- DYNAMIC_START -->
<!-- DYNAMIC_END -->
"""


def build_dynamic_content() -> str:
    db_path = get_db_path("logistics")

    try:
        with sqlite3.connect(db_path) as conn:
            # 最新一条记录
            latest = conn.execute("""
                SELECT week_start, week_end, iso_year, iso_week,
                       rail_freight, highway_trucks, port_cargo,
                       container_throughput, flights_total,
                       express_pickup, express_delivery,
                       source_url
                FROM weekly_data
                ORDER BY week_start DESC
                LIMIT 1
            """).fetchone()

            # 数据范围
            extent = conn.execute("""
                SELECT MIN(week_start), MAX(week_start),
                       MIN(iso_year)||'-W'||printf('%02d',MIN(iso_week)),
                       MAX(iso_year)||'-W'||printf('%02d',MAX(iso_week)),
                       COUNT(*)
                FROM weekly_data
            """).fetchone()

    except Exception as e:
        return f"\n> 数据暂无 ({e})\n"

    if not latest:
        return "\n> 数据库为空，请先运行回填脚本。\n"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    (ws, we, iso_yr, iso_wk,
     rail, trucks, port, container,
     flights, pickup, delivery, src_url) = latest
    min_ws, max_ws, min_wk, max_wk, total_weeks = extent

    lines = [
        f"\n**最后更新：{now}**\n",
        f"\n### 最近一期数据（{ws} ~ {we}，ISO {iso_yr}-W{iso_wk:02d}）\n",
        "| 指标 | 本周值 |",
        "|------|--------|",
    ]

    def fmt(v, unit):
        return f"{v:.2f} {unit}" if v is not None else "N/A"

    lines += [
        f"| 铁路货运量 | {fmt(rail, '万吨')} |",
        f"| 高速公路货车通行量 | {fmt(trucks, '万辆')} |",
        f"| 港口货物吞吐量 | {fmt(port, '万吨')} |",
        f"| 集装箱吞吐量 | {fmt(container, '万TEU')} |",
        f"| 民航航班数 | {fmt(flights, '万班')} |",
        f"| 快递揽收量 | {fmt(pickup, '亿件')} |",
        f"| 快递投递量 | {fmt(delivery, '亿件')} |",
        "",
        f"> 数据来源：[交通运输部通报]({src_url})\n",
    ]

    lines += [
        "### 核心图表\n",
        "**铁路货运量**",
        "![铁路货运量](charts/rail_freight_yoy.png)\n",
        "**港口货物吞吐量**",
        "![港口货物吞吐量](charts/port_cargo_yoy.png)\n",
        "**快递量**",
        "![快递揽收量](charts/express_pickup_yoy.png)\n",
        "**YTD 累计同比增速**",
        "![YTD增速对比](charts/ytd_growth_comparison.png)\n",
    ]

    lines += [
        f"\n### 数据覆盖范围\n",
        f"从 **{min_wk}** 到 **{max_wk}**，共 **{total_weeks}** 周\n",
    ]

    return "\n".join(lines)


def generate_readme():
    dynamic = build_dynamic_content()
    dynamic_block = f"<!-- DYNAMIC_START -->\n{dynamic}\n<!-- DYNAMIC_END -->"

    if README_PATH.exists():
        old = README_PATH.read_text(encoding="utf-8")
        import re
        new = re.sub(
            r"<!-- DYNAMIC_START -->.*?<!-- DYNAMIC_END -->",
            dynamic_block,
            old,
            flags=re.DOTALL,
        )
        if new == old:
            # 静态部分一致，只更新动态
            README_PATH.write_text(new, encoding="utf-8")
        else:
            README_PATH.write_text(new, encoding="utf-8")
    else:
        # 首次创建：写入完整静态+动态内容
        full = STATIC_CONTENT.replace(
            "<!-- DYNAMIC_START -->\n<!-- DYNAMIC_END -->",
            dynamic_block,
        )
        README_PATH.write_text(full, encoding="utf-8")

    print(f"[readme] README.md 已更新: {README_PATH}")


if __name__ == "__main__":
    generate_readme()
