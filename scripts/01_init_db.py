"""
01_init_db.py — 初始化 SQLite 数据库
幂等操作，可重复运行。
"""
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import get_db_path

LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_links (
    url TEXT PRIMARY KEY,
    title TEXT,
    index_page TEXT,
    discovered_at TEXT,
    fetched INTEGER DEFAULT 0,
    fetched_at TEXT
);
"""

DAILY_RAW_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date DATE NOT NULL UNIQUE,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    year INTEGER NOT NULL,
    publish_date DATE,

    rail_freight REAL,
    highway_trucks REAL,
    port_cargo REAL,
    container_throughput REAL,
    flights_total REAL,
    cargo_flights INTEGER,
    intl_cargo_flights INTEGER,
    domestic_cargo_flights INTEGER,
    express_pickup REAL,
    express_delivery REAL,

    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

LOGISTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    year INTEGER NOT NULL,
    publish_date DATE,

    rail_freight REAL,
    highway_trucks REAL,
    port_cargo REAL,
    container_throughput REAL,
    flights_total REAL,
    cargo_flights INTEGER,
    intl_cargo_flights INTEGER,
    domestic_cargo_flights INTEGER,
    express_pickup REAL,
    express_delivery REAL,

    rail_freight_wow REAL,
    highway_trucks_wow REAL,
    port_cargo_wow REAL,
    container_throughput_wow REAL,
    flights_total_wow REAL,
    express_pickup_wow REAL,
    express_delivery_wow REAL,

    source_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(iso_year, iso_week)
);
"""


def init_db():
    links_path = get_db_path("links")
    logistics_path = get_db_path("logistics")

    with sqlite3.connect(links_path) as conn:
        conn.execute(LINKS_SCHEMA)
        conn.commit()
    print(f"[init_db] links.db ready at {links_path}")

    with sqlite3.connect(logistics_path) as conn:
        conn.execute(LOGISTICS_SCHEMA)
        conn.execute(DAILY_RAW_SCHEMA)
        conn.commit()
    print(f"[init_db] logistics.db ready at {logistics_path}")


if __name__ == "__main__":
    init_db()
