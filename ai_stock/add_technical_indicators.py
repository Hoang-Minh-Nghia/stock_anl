"""Bước 2: tính chỉ báo kỹ thuật cho toàn bộ lịch sử giá.

    python ai_stock/add_technical_indicators.py
"""

import pandas as pd

from features import INDICATORS_FILE, PRICE_MASTER, compute_indicators


def main():
    if not PRICE_MASTER.exists():
        print(f"❌ Chưa có {PRICE_MASTER}. Chạy get_stock_name.py trước.")
        return
    prices = pd.read_csv(PRICE_MASTER, parse_dates=["time"])
    print(f"📊 {len(prices):,} dòng · {prices['ticker'].nunique()} mã")
    result = compute_indicators(prices)
    result.to_csv(INDICATORS_FILE, index=False)
    print(f"✅ {INDICATORS_FILE} · {len(result.columns)} cột")


if __name__ == "__main__":
    main()
