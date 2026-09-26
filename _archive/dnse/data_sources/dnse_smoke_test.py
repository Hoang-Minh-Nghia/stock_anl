"""Kiểm tra nhanh kết nối DNSE.

Chạy từ thư mục gốc project:
    python -m data_sources.dnse_smoke_test            # gọi API thật (cần .env)
    python -m data_sources.dnse_smoke_test --offline  # chỉ kiểm tra thuật toán ký
"""

import sys

from .dnse_client import DNSEError, DNSEMarketDataClient, build_signature


def check_signature():
    # Signing string phải khớp đúng định dạng trong tài liệu DNSE
    sig = build_signature(
        "test-secret",
        "GET",
        "/price/ohlc",
        "Fri, 15 May 2026 07:11:30 +0000",
        "c9a8f88b472c9721fde161e0d89df8cc",
    )
    assert sig and "+" not in sig and "/" not in sig and "=" not in sig, sig
    print(f"[OK] Signature format: {sig}")


def check_live():
    try:
        client = DNSEMarketDataClient()
    except DNSEError as exc:
        print(f"[SKIP] {exc}")
        return 1

    try:
        df = client.get_ohlc("HPG", start="2026-01-01", resolution="1D")
        print(f"[OK] OHLC HPG 1D: {len(df)} nến, {df['time'].min()} -> {df['time'].max()}")
        print(df.tail(3).to_string(index=False))

        idx = client.get_ohlc("VNINDEX", start="2026-08-01", resolution="1D")
        print(f"[OK] OHLC VNINDEX: {len(idx)} nến, close cuối = {idx['close'].iloc[-1] if len(idx) else None}")

        vn100 = client.get_index_constituents("VN100")
        print(f"[OK] VN100: {len(vn100)} mã, ví dụ {vn100[:10]}")

        print(f"     Rate limit còn lại: {client.rate_limit_remaining}")
    except DNSEError as exc:
        print(f"[FAIL] {exc}")
        if exc.status == 400:
            print("       Nếu lỗi OA-400, thử đặt DNSE_DATE_HEADER=X-Aux-Date trong .env")
        return 1
    return 0


if __name__ == "__main__":
    check_signature()
    if "--offline" in sys.argv:
        sys.exit(0)
    sys.exit(check_live())
