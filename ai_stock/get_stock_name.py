"""Làm mới danh sách VN100 (VPS) rồi cập nhật dữ liệu giá + chỉ báo.

    python ai_stock/get_stock_name.py

Mã mới vào rổ sẽ được tải toàn bộ lịch sử; mã đã có chỉ tải ngày còn thiếu.
"""

import pandas as pd
import requests

from features import DATA_DIR, VN100_LIST_FILE
from run_daily_update import update


def get_vn100_symbols():
    try:
        resp = requests.get("https://bgapidatafeed.vps.com.vn/getlistckindex/VN100", timeout=15)
        resp.raise_for_status()
        symbols = [s for s in resp.json() if isinstance(s, str)]
        if len(symbols) >= 50:
            print(f"✅ Danh sách VN100 từ VPS: {len(symbols)} mã")
            return symbols
    except (requests.RequestException, ValueError) as exc:
        print(f"⚠️ Lỗi lấy VN100 ({exc})")
    if VN100_LIST_FILE.exists():
        symbols = pd.read_csv(VN100_LIST_FILE)["ticker"].tolist()
        print(f"   Dùng danh sách đã lưu: {len(symbols)} mã")
        return symbols
    return []


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    symbols = get_vn100_symbols()
    if not symbols:
        print("❌ Không có danh sách mã.")
        return
    pd.DataFrame({"ticker": symbols}).to_csv(VN100_LIST_FILE, index=False)
    update(symbols)


if __name__ == "__main__":
    main()
