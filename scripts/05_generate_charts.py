"""
05_generate_charts.py — 生成可视化图表

图表:
  - 各核心指标年度同期对比图 (yoy)
  - YTD 累计同比增速对比图
"""
import sqlite3
from pathlib import Path
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_db_path, setup_chinese_font

ROOT = Path(__file__).resolve().parent.parent
CHARTS_DIR = ROOT / "charts"
CHARTS_DIR.mkdir(exist_ok=True)

# 颜色调色板（区分度高）
COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b"]

CHINESE_SUPPORTED = setup_chinese_font()

# 指标配置
INDICATORS = [
    {
        "col": "rail_freight",
        "label_zh": "国家铁路货运量",
        "label_en": "Rail Freight Volume",
        "unit_zh": "万吨",
        "unit_en": "10k tons",
        "chart": "rail_freight_yoy.png",
    },
    {
        "col": "highway_trucks",
        "label_zh": "高速公路货车通行量",
        "label_en": "Highway Truck Volume",
        "unit_zh": "万辆",
        "unit_en": "10k vehicles",
        "chart": "highway_trucks_yoy.png",
    },
    {
        "col": "port_cargo",
        "label_zh": "港口货物吞吐量",
        "label_en": "Port Cargo Throughput",
        "unit_zh": "万吨",
        "unit_en": "10k tons",
        "chart": "port_cargo_yoy.png",
    },
    {
        "col": "container_throughput",
        "label_zh": "集装箱吞吐量",
        "label_en": "Container Throughput",
        "unit_zh": "万TEU",
        "unit_en": "10k TEU",
        "chart": "container_yoy.png",
    },
    {
        "col": "flights_total",
        "label_zh": "民航航班数",
        "label_en": "Civil Aviation Flights",
        "unit_zh": "万班",
        "unit_en": "10k flights",
        "chart": "aviation_yoy.png",
    },
    {
        "col": "express_pickup",
        "label_zh": "快递揽收量",
        "label_en": "Express Pickup Volume",
        "unit_zh": "亿件",
        "unit_en": "100M parcels",
        "chart": "express_pickup_yoy.png",
    },
    {
        "col": "express_delivery",
        "label_zh": "快递投递量",
        "label_en": "Express Delivery Volume",
        "unit_zh": "亿件",
        "unit_en": "100M parcels",
        "chart": "express_delivery_yoy.png",
    },
]


def load_data() -> pd.DataFrame:
    db_path = get_db_path("logistics")
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT * FROM weekly_data ORDER BY week_start",
            conn,
            parse_dates=["week_start", "week_end", "publish_date"],
        )
    return df


def label(zh: str, en: str) -> str:
    return zh if CHINESE_SUPPORTED else en


def plot_yoy(df: pd.DataFrame, indicator: dict):
    col = indicator["col"]
    title = label(indicator["label_zh"], indicator["label_en"])
    unit = label(indicator["unit_zh"], indicator["unit_en"])

    sub = df[["iso_year", "iso_week", col]].dropna(subset=[col])
    if sub.empty:
        print(f"[charts] 无数据，跳过: {col}")
        return

    years = sorted(sub["iso_year"].unique())
    # 只展示近3年
    recent_years = years[-3:] if len(years) >= 3 else years

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.set_facecolor("#f8f8f8")
    fig.patch.set_facecolor("white")

    for i, year in enumerate(recent_years):
        ydata = sub[sub["iso_year"] == year].sort_values("iso_week")
        color = COLORS[i % len(COLORS)]
        ax.plot(
            ydata["iso_week"],
            ydata[col],
            marker="o",
            markersize=3,
            linewidth=1.8,
            color=color,
            label=str(year),
        )
        # 标注最新数据点
        if not ydata.empty:
            last = ydata.iloc[-1]
            ax.annotate(
                f"{last[col]:.1f}",
                xy=(last["iso_week"], last[col]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7,
                color=color,
            )

    ax.set_xlabel(label("ISO 周", "ISO Week"), fontsize=10)
    ax.set_ylabel(unit, fontsize=10)
    ax.set_title(
        label(f"{title}（周度同期对比）", f"{title} — Year-over-Year Comparison"),
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.legend(title=label("年份", "Year"), fontsize=9)
    ax.grid(True, alpha=0.4, linestyle="--")
    ax.set_xlim(1, 53)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
    plt.tight_layout()

    out_path = CHARTS_DIR / indicator["chart"]
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[charts] 保存: {out_path.name}")


def plot_ytd_growth(df: pd.DataFrame):
    """YTD 累计同比增速对比图"""
    years = sorted(df["iso_year"].unique())
    if len(years) < 2:
        print("[charts] 数据不足两年，跳过 YTD 增速图")
        return

    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
    ax.set_facecolor("#f8f8f8")
    fig.patch.set_facecolor("white")

    current_year = max(years)
    prev_year = current_year - 1

    plotted = 0
    for i, ind in enumerate(INDICATORS):
        col = ind["col"]
        lbl = label(ind["label_zh"], ind["label_en"])

        cur = df[df["iso_year"] == current_year][["iso_week", col]].dropna().sort_values("iso_week")
        prv = df[df["iso_year"] == prev_year][["iso_week", col]].dropna().sort_values("iso_week")

        if cur.empty or prv.empty:
            continue

        # YTD 累计
        cur = cur.copy()
        prv = prv.copy()
        cur["ytd"] = cur[col].cumsum()
        prv["ytd"] = prv[col].cumsum()

        merged = cur.merge(prv, on="iso_week", suffixes=("_cur", "_prv"))
        merged = merged[merged["ytd_prv"] > 0]
        if merged.empty:
            continue

        merged["yoy_pct"] = (merged["ytd_cur"] / merged["ytd_prv"] - 1) * 100

        ax.plot(
            merged["iso_week"],
            merged["yoy_pct"],
            marker="o",
            markersize=3,
            linewidth=1.8,
            color=COLORS[i % len(COLORS)],
            label=lbl,
        )
        plotted += 1

    if plotted == 0:
        print("[charts] YTD 图无数据，跳过")
        plt.close(fig)
        return

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel(label("ISO 周", "ISO Week"), fontsize=10)
    ax.set_ylabel(label("YTD 同比增速 (%)", "YTD YoY Growth (%)"), fontsize=10)
    ax.set_title(
        label(
            f"各指标年初至今累计同比增速（{current_year} vs {prev_year}）",
            f"YTD Cumulative YoY Growth ({current_year} vs {prev_year})",
        ),
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.4, linestyle="--")
    ax.set_xlim(1, 53)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
    plt.tight_layout()

    out_path = CHARTS_DIR / "ytd_growth_comparison.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[charts] 保存: {out_path.name}")


def generate_charts():
    print("[charts] 读取数据库...")
    df = load_data()
    if df.empty:
        print("[charts] 数据库为空，无法生成图表")
        return

    print(f"[charts] 共 {len(df)} 条记录，开始生成图表...")

    for ind in INDICATORS:
        plot_yoy(df, ind)

    plot_ytd_growth(df)

    print(f"[charts] 所有图表已保存至 {CHARTS_DIR}")


if __name__ == "__main__":
    generate_charts()
