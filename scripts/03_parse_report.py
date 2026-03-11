"""
03_parse_report.py — 解析通报详情页，提取结构化数据

用法:
  python scripts/03_parse_report.py --url URL   # 解析单个 URL
  python scripts/03_parse_report.py --pending   # 处理所有未抓取的链接
"""
import argparse
import datetime
import re
import sqlite3
import time
from pathlib import Path
import sys

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_db_path, normalize_number, parse_date_range, calc_iso_week

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        print(f"[parse_report] 请求失败 {url}: {e}")
        return None


def extract_wow(text: str, after_pattern: str) -> float | None:
    """
    在 after_pattern 之后查找 环比增长/下降 X.XX%
    返回带符号浮点数，找不到返回 None
    """
    idx = text.find(after_pattern)
    if idx == -1:
        return None
    snippet = text[idx: idx + 60]
    m = re.search(r"环比(增长|下降)([\d.]+)%", snippet)
    if not m:
        return None
    value = float(normalize_number(m.group(2)))
    return value if m.group(1) == "增长" else -value


def parse_report(html: str, url: str) -> dict | None:
    """解析通报 HTML，返回结构化数据 dict，失败返回 None"""
    soup = BeautifulSoup(html, "html.parser")

    # 1. 提取发布日期
    publish_date = None
    full_text = soup.get_text()
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}", full_text)
    if date_m:
        try:
            publish_date = datetime.date.fromisoformat(date_m.group(1))
        except ValueError:
            pass

    if publish_date is None:
        print(f"[parse_report] 无法提取发布日期: {url}")
        return None

    # 2. 提取标题
    title_el = soup.find("h1")
    if not title_el:
        # 备用：页面 <title>
        title_el = soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""

    # 3. 解析日期范围
    week_start, week_end = parse_date_range(title, publish_date)
    if week_start is None:
        print(f"[parse_report] 无法解析日期范围 '{title}': {url}")
        return None

    iso_year, iso_week = calc_iso_week(week_start)

    # 4. 提取正文文本（合并所有段落）
    content_div = soup.find("div", id="Zoom") or soup.find("div", class_="detail-content")
    if content_div:
        content_text = content_div.get_text(separator=" ")
    else:
        content_text = full_text

    content_text = normalize_number(content_text)

    # 5. 提取各项指标
    def find_float(patterns: list[str]) -> float | None:
        for pat in patterns:
            m = re.search(pat, content_text)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, IndexError):
                    pass
        return None

    def find_int(patterns: list[str]) -> int | None:
        for pat in patterns:
            m = re.search(pat, content_text)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    pass
        return None

    # 铁路货运量（万吨）—— 新格式优先，累计格式兜底
    rail_freight = find_float([
        r"国家铁路运输货物([\d.]+)万吨",
        r"铁路运输货物([\d.]+)万吨",
        r"国家铁路累计运输货物([\d.]+)万吨",
        r"铁路累计运输货物([\d.]+)万吨",
    ])

    # 高速公路货车通行量（万辆）
    highway_trucks = find_float([
        r"全国高速公路货车通行([\d.]+)万辆",
        r"高速公路货车通行([\d.]+)万辆",
        r"全国高速公路累计货车通行([\d.]+)万辆",
        r"高速公路累计货车通行([\d.]+)万辆",
    ])

    # 港口货物吞吐量（万吨）
    port_cargo = find_float([
        r"监测港口完成货物吞吐量([\d.]+)万吨",
        r"港口完成货物吞吐量([\d.]+)万吨",
        r"监测港口累计完成货物吞吐量([\d.]+)万吨",
        r"港口累计完成货物吞吐量([\d.]+)万吨",
        r"累计完成货物吞吐量([\d.]+)万吨",
        r"货物吞吐量([\d.]+)万吨",
    ])

    # 集装箱吞吐量（万TEU）
    container_throughput = find_float([
        r"完成集装箱吞吐量([\d.]+)万标箱",
        r"集装箱吞吐量([\d.]+)万标箱",
        r"累计完成集装箱吞吐量([\d.]+)万标箱",
        r"集装箱吞吐量([\d.]+)万TEU",
    ])

    # 民航航班总数（万班）
    flights_total = find_float([
        r"民航保障航班([\d.]+)万班",
        r"保障航班([\d.]+)万班",
        r"民航累计保障航班([\d.]+)万班",
        r"累计保障航班([\d.]+)万班",
    ])

    # 货运航班（班）
    cargo_flights = find_int([
        r"其中货运航班(\d+)班",
        r"货运航班(\d+)班",
    ])

    # 国际货运航班（班）
    intl_cargo_flights = find_int([
        r"国际货运航班(\d+)班",
    ])

    # 国内货运航班（班）
    domestic_cargo_flights = find_int([
        r"国内货运航班(\d+)班",
    ])

    # 快递揽收量（亿件）
    express_pickup = find_float([
        r"邮政快递揽收量约([\d.]+)亿件",
        r"快递揽收量约([\d.]+)亿件",
        r"揽收量约([\d.]+)亿件",
        r"邮政快递累计揽收量约([\d.]+)亿件",
        r"快递累计揽收量约([\d.]+)亿件",
        r"累计揽收量约([\d.]+)亿件",
    ])

    # 快递投递量（亿件）
    express_delivery = find_float([
        r"投递量约([\d.]+)亿件",
        r"快递投递量约([\d.]+)亿件",
        r"累计投递量约([\d.]+)亿件",
        r"快递累计投递量约([\d.]+)亿件",
    ])

    # 6. 提取环比（新格式 anchor 优先，累计格式兜底）
    rail_freight_wow = (
        extract_wow(content_text, "国家铁路运输货物")
        or extract_wow(content_text, "铁路运输货物")
        or extract_wow(content_text, "国家铁路累计运输货物")
    )
    highway_trucks_wow = (
        extract_wow(content_text, "高速公路货车通行")
        or extract_wow(content_text, "高速公路累计货车通行")
    )
    port_cargo_wow = (
        extract_wow(content_text, "货物吞吐量")
        or extract_wow(content_text, "累计完成货物吞吐量")
    )
    container_throughput_wow = extract_wow(content_text, "集装箱吞吐量")
    flights_total_wow = (
        extract_wow(content_text, "民航保障航班")
        or extract_wow(content_text, "保障航班")
        or extract_wow(content_text, "民航累计保障航班")
    )
    express_pickup_wow = (
        extract_wow(content_text, "揽收量约")
        or extract_wow(content_text, "累计揽收量约")
    )
    express_delivery_wow = (
        extract_wow(content_text, "投递量约")
        or extract_wow(content_text, "累计投递量约")
    )

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "iso_year": iso_year,
        "iso_week": iso_week,
        "year": publish_date.year,
        "publish_date": publish_date.isoformat(),
        "rail_freight": rail_freight,
        "highway_trucks": highway_trucks,
        "port_cargo": port_cargo,
        "container_throughput": container_throughput,
        "flights_total": flights_total,
        "cargo_flights": cargo_flights,
        "intl_cargo_flights": intl_cargo_flights,
        "domestic_cargo_flights": domestic_cargo_flights,
        "express_pickup": express_pickup,
        "express_delivery": express_delivery,
        "rail_freight_wow": rail_freight_wow,
        "highway_trucks_wow": highway_trucks_wow,
        "port_cargo_wow": port_cargo_wow,
        "container_throughput_wow": container_throughput_wow,
        "flights_total_wow": flights_total_wow,
        "express_pickup_wow": express_pickup_wow,
        "express_delivery_wow": express_delivery_wow,
        "source_url": url,
    }


ADDITIVE_METRICS = [
    "rail_freight", "highway_trucks", "port_cargo", "container_throughput",
    "flights_total", "cargo_flights", "intl_cargo_flights", "domestic_cargo_flights",
    "express_pickup", "express_delivery",
]


def save_to_db(data: dict):
    """保存周度报告到 weekly_data 表。"""
    db_path = get_db_path("logistics")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO weekly_data (
                week_start, week_end, iso_year, iso_week, year, publish_date,
                rail_freight, highway_trucks, port_cargo, container_throughput,
                flights_total, cargo_flights, intl_cargo_flights, domestic_cargo_flights,
                express_pickup, express_delivery,
                rail_freight_wow, highway_trucks_wow, port_cargo_wow,
                container_throughput_wow, flights_total_wow,
                express_pickup_wow, express_delivery_wow,
                source_url
            ) VALUES (
                :week_start, :week_end, :iso_year, :iso_week, :year, :publish_date,
                :rail_freight, :highway_trucks, :port_cargo, :container_throughput,
                :flights_total, :cargo_flights, :intl_cargo_flights, :domestic_cargo_flights,
                :express_pickup, :express_delivery,
                :rail_freight_wow, :highway_trucks_wow, :port_cargo_wow,
                :container_throughput_wow, :flights_total_wow,
                :express_pickup_wow, :express_delivery_wow,
                :source_url
            )
        """, data)
        conn.commit()


def save_daily_raw(data: dict):
    """保存单日报告到 daily_raw 表，然后聚合该 ISO 周到 weekly_data。"""
    db_path = get_db_path("logistics")
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO daily_raw (
                report_date, iso_year, iso_week, year, publish_date,
                rail_freight, highway_trucks, port_cargo, container_throughput,
                flights_total, cargo_flights, intl_cargo_flights, domestic_cargo_flights,
                express_pickup, express_delivery,
                source_url
            ) VALUES (
                :week_start, :iso_year, :iso_week, :year, :publish_date,
                :rail_freight, :highway_trucks, :port_cargo, :container_throughput,
                :flights_total, :cargo_flights, :intl_cargo_flights, :domestic_cargo_flights,
                :express_pickup, :express_delivery,
                :source_url
            )
        """, data)
        conn.commit()
    # 聚合该周所有日数据到 weekly_data
    aggregate_daily_to_weekly(data["iso_year"], data["iso_week"])


def aggregate_daily_to_weekly(iso_year: int, iso_week: int):
    """
    将 daily_raw 中属于同一 ISO 周的记录求和，写入 weekly_data。
    只写可加字段（货运量、件数等），WoW 字段保留 NULL。
    """
    db_path = get_db_path("logistics")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM daily_raw WHERE iso_year=? AND iso_week=? ORDER BY report_date",
            (iso_year, iso_week),
        ).fetchall()

    if not rows:
        return

    # 聚合：对各加总字段求 SUM（忽略 NULL），保留第一行的元信息
    agg: dict = {}
    for metric in ADDITIVE_METRICS:
        values = [r[metric] for r in rows if r[metric] is not None]
        if metric in ("cargo_flights", "intl_cargo_flights", "domestic_cargo_flights"):
            agg[metric] = int(sum(values)) if values else None
        else:
            agg[metric] = round(sum(values), 4) if values else None

    week_start = rows[0]["report_date"]
    week_end   = rows[-1]["report_date"]
    year       = rows[-1]["year"]
    publish_date = rows[-1]["publish_date"]
    source_urls  = "; ".join(r["source_url"] for r in rows if r["source_url"])

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO weekly_data (
                week_start, week_end, iso_year, iso_week, year, publish_date,
                rail_freight, highway_trucks, port_cargo, container_throughput,
                flights_total, cargo_flights, intl_cargo_flights, domestic_cargo_flights,
                express_pickup, express_delivery,
                rail_freight_wow, highway_trucks_wow, port_cargo_wow,
                container_throughput_wow, flights_total_wow,
                express_pickup_wow, express_delivery_wow,
                source_url
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                ?
            )
        """, (
            week_start, week_end, iso_year, iso_week, year, publish_date,
            agg["rail_freight"], agg["highway_trucks"], agg["port_cargo"],
            agg["container_throughput"], agg["flights_total"],
            agg["cargo_flights"], agg["intl_cargo_flights"], agg["domestic_cargo_flights"],
            agg["express_pickup"], agg["express_delivery"],
            source_urls,
        ))
        conn.commit()
    print(f"[parse_report]   [聚合] ISO {iso_year}-W{iso_week:02d}: "
          f"{len(rows)} 天 → week_start={week_start}, week_end={week_end}")


def update_link_status(url: str, status: int):
    db_path = get_db_path("links")
    now = datetime.datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE report_links SET fetched=?, fetched_at=? WHERE url=?",
            (status, now, url),
        )
        conn.commit()


def process_url(url: str) -> bool:
    print(f"[parse_report] 处理: {url}")
    html = fetch_html(url)
    if html is None:
        update_link_status(url, -1)
        return False

    data = parse_report(html, url)
    if data is None:
        update_link_status(url, -1)
        return False

    is_daily = (data["week_start"] == data["week_end"])
    if is_daily:
        save_daily_raw(data)
        print(f"[parse_report]   单日 {data['week_start']} → daily_raw "
              f"(ISO {data['iso_year']}-W{data['iso_week']:02d})")
    else:
        save_to_db(data)
        print(f"[parse_report]   保存 {data['week_start']} ~ {data['week_end']} "
              f"(ISO {data['iso_year']}-W{data['iso_week']:02d})")

    update_link_status(url, 1)
    return True


def process_pending(sleep: float = 1.0) -> tuple[int, int]:
    db_path = get_db_path("links")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT url FROM report_links WHERE fetched=0 ORDER BY discovered_at"
        ).fetchall()

    urls = [r[0] for r in rows]
    print(f"[parse_report] 待处理 {len(urls)} 条链接")

    ok, fail = 0, 0
    for i, url in enumerate(urls, 1):
        print(f"[parse_report] [{i}/{len(urls)}]", end=" ")
        if process_url(url):
            ok += 1
        else:
            fail += 1
        if i < len(urls):
            time.sleep(sleep)

    print(f"[parse_report] 完成: 成功 {ok}，失败 {fail}")
    return ok, fail


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="解析单个通报 URL")
    group.add_argument("--pending", action="store_true", help="处理所有未抓取链接")
    parser.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()

    if args.url:
        process_url(args.url)
    else:
        process_pending(sleep=args.sleep)
