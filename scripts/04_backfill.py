"""
04_backfill.py — 批量回填历史数据（首次运行）

用法:
  python scripts/04_backfill.py
  python scripts/04_backfill.py --sleep 2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib

fetch_index_mod = importlib.import_module("02_fetch_index")
parse_report_mod = importlib.import_module("03_parse_report")


def backfill(sleep: float = 1.0):
    print("=" * 60)
    print("[backfill] 步骤 1/2: 抓取所有索引页")
    print("=" * 60)
    total_new = fetch_index_mod.fetch_index(max_pages=0, sleep=sleep)
    print(f"[backfill] 索引抓取完成，共新增 {total_new} 条链接\n")

    print("=" * 60)
    print("[backfill] 步骤 2/2: 解析所有待处理通报")
    print("=" * 60)
    ok, fail = parse_report_mod.process_pending(sleep=sleep)
    print(f"\n[backfill] 回填完成: 成功 {ok} 篇，失败 {fail} 篇")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒数")
    args = parser.parse_args()
    backfill(sleep=args.sleep)
