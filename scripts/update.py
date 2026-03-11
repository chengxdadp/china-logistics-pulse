"""
update.py — 增量更新流水线

用法:
  python scripts/update.py                  # 增量更新（抓最近3页索引）
  python scripts/update.py --full           # 完整回填
  python scripts/update.py --charts-only   # 只重新生成图表和 README
  python scripts/update.py --sleep 2        # 自定义请求间隔
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib

fetch_index_mod = importlib.import_module("02_fetch_index")
parse_report_mod = importlib.import_module("03_parse_report")
backfill_mod = importlib.import_module("04_backfill")
charts_mod = importlib.import_module("05_generate_charts")
readme_mod = importlib.import_module("06_generate_readme")

# 确保数据库已初始化
init_db_mod = importlib.import_module("01_init_db")


def run(args):
    # 始终确保数据库存在
    init_db_mod.init_db()

    if args.charts_only:
        print("\n[update] === 仅重新生成图表和 README ===")
        charts_mod.generate_charts()
        readme_mod.generate_readme()
        return

    if args.full:
        print("\n[update] === 完整回填模式 ===")
        backfill_mod.backfill(sleep=args.sleep)
    else:
        print("\n[update] === 增量更新模式 ===")
        print("[update] 步骤 1/2: 获取最近索引页...")
        fetch_index_mod.fetch_index(max_pages=3, sleep=args.sleep)

        print("\n[update] 步骤 2/2: 解析待处理通报...")
        parse_report_mod.process_pending(sleep=args.sleep)

    print("\n[update] 步骤 3: 生成图表...")
    charts_mod.generate_charts()

    print("\n[update] 步骤 4: 更新 README...")
    readme_mod.generate_readme()

    print("\n[update] 全部完成！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="China Logistics Pulse 更新脚本")
    parser.add_argument("--full", action="store_true", help="完整回填所有历史数据")
    parser.add_argument("--charts-only", action="store_true", help="只重新生成图表和 README")
    parser.add_argument("--sleep", type=float, default=1.0, help="请求间隔秒数（默认 1.0）")
    args = parser.parse_args()
    run(args)
