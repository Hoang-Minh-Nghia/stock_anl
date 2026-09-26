"""Ghép bối cảnh thị trường (VNINDEX + nhóm ngành dẫn dắt) vào dữ liệu chỉ báo.

    python ai_stock/add_macro_sector_data.py [--no-update]

Không dùng dữ liệu tương lai: ngày thiếu bối cảnh được điền 0, không back-fill.
"""

import argparse

import pandas as pd

from features import INDICATORS_FILE, MACRO_FILE, MARKET_CONTEXT_FILE, PRICE_MASTER, add_market_context, build_market_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-update", action="store_true", help="Không tải thêm giá VNINDEX/mã đầu ngành")
    args = parser.parse_args()
    if not INDICATORS_FILE.exists():
        print(f"❌ Chưa có {INDICATORS_FILE}. Chạy run_daily_update.py trước.")
        return
    prices = pd.read_csv(PRICE_MASTER, parse_dates=["time"])
    context = build_market_context(prices, update=not args.no_update)
    context.to_csv(MARKET_CONTEXT_FILE, index=False)
    merged = add_market_context(pd.read_csv(INDICATORS_FILE, parse_dates=["time"]), context)
    merged.to_csv(MACRO_FILE, index=False)
    print(f"✅ {MACRO_FILE} · {len(merged):,} dòng · {merged['time'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
