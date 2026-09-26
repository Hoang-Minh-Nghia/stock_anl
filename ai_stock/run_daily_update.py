"""Cập nhật dữ liệu AI: giá VN100 (chỉ tải ngày còn thiếu) → chỉ báo kỹ thuật → bối cảnh thị trường.

    python ai_stock/run_daily_update.py

Giá lấy từ kho cục bộ `data/prices/` dùng chung với Smart Money. Kho tự tải lại toàn bộ lịch sử
một mã khi SSI điều chỉnh giá quá khứ (cổ tức, thưởng cổ phiếu) → không có bước nhảy giá giả.
"""

import pandas as pd

from features import (
    INDICATORS_FILE, MACRO_FILE, MARKET_CONTEXT_FILE, PRICE_MASTER, VN100_LIST_FILE, add_market_context,
    build_market_context, compute_indicators, load_prices, price_store,
)


def update(tickers=None):
    if tickers is None:
        if not VN100_LIST_FILE.exists():
            print("❌ Chưa có danh sách VN100. Chạy get_stock_name.py trước.")
            return None
        tickers = pd.read_csv(VN100_LIST_FILE)["ticker"].tolist()

    seeded = price_store.seed_from_master(PRICE_MASTER) if not price_store.PRICE_DIR.exists() else 0
    if seeded:
        print(f"   Khởi tạo kho giá từ dữ liệu có sẵn: {seeded} mã")

    print(f"📈 Cập nhật giá {len(tickers)} mã (chỉ tải ngày còn thiếu)...")
    prices, stats = load_prices(tickers)
    print(f"   {price_store.describe_stats(stats)}")
    if prices.empty:
        print("❌ Không có dữ liệu giá.")
        return None
    prices.to_csv(PRICE_MASTER, index=False)

    print("🔧 Chỉ báo kỹ thuật + bối cảnh thị trường...")
    indicators = compute_indicators(prices)
    indicators.to_csv(INDICATORS_FILE, index=False)
    context = build_market_context(prices)
    context.to_csv(MARKET_CONTEXT_FILE, index=False)
    merged = add_market_context(indicators, context)
    merged.to_csv(MACRO_FILE, index=False)
    print(f"✅ Dữ liệu AI tới {merged['time'].max():%Y-%m-%d} · {prices['ticker'].nunique()} mã")
    return merged


if __name__ == "__main__":
    update()
