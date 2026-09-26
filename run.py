"""Chạy toàn bộ trên máy: cập nhật dữ liệu còn thiếu → phân tích → mở dashboard.

    python run.py              # Smart Money + cập nhật dữ liệu AI + dự báo (nếu đã huấn luyện mô hình)
    python run.py --serve      # như trên, xong mở dashboard trên trình duyệt
    python run.py --serve-only # chỉ mở dashboard với dữ liệu đã có
    python run.py --no-ai      # bỏ qua phần AI

Không cần server hay tài khoản cloud. Toàn bộ dữ liệu nằm trong thư mục dự án.
"""

import argparse
import functools
import http.server
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "anal_stock" / "public"
AI_DIR = ROOT / "ai_stock"


def run_ai_step(script, *args):
    cmd = [sys.executable, "-u", str(AI_DIR / script), *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "TF_CPP_MIN_LOG_LEVEL": "2", "TF_ENABLE_ONEDNN_OPTS": "0"}
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    return result.returncode == 0


def serve(port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PUBLIC_DIR))
    handler.log_message = lambda *a, **k: None
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        url = f"http://127.0.0.1:{port}/"
        print(f"Cổng {port} đang được dùng (có thể dashboard đã mở sẵn): {url}")
        webbrowser.open(url)
        return
    url = f"http://127.0.0.1:{port}/"
    print(f"\n🌐 Dashboard: {url}  (Ctrl+C để dừng)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng dashboard.")


def main():
    from smart_money.pipeline import ensure_utf8_stdout

    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Chạy phân tích cổ phiếu cục bộ")
    parser.add_argument("--serve", action="store_true", help="Mở dashboard sau khi chạy xong")
    parser.add_argument("--serve-only", action="store_true", help="Chỉ mở dashboard")
    parser.add_argument("--no-ai", action="store_true", help="Bỏ qua cập nhật dữ liệu & dự báo AI")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not args.serve_only:
        started = time.time()
        from market_data import price_store
        from smart_money import pipeline

        if not price_store.PRICE_DIR.exists():
            seeded = price_store.seed_from_master(AI_DIR / "data" / "vn100_price_master.csv")
            if seeded:
                print(f"Khởi tạo kho giá từ dữ liệu AI có sẵn: {seeded} mã")

        try:
            pipeline.run()
        except Exception as exc:  # vẫn tiếp tục phần AI / dashboard với dữ liệu cũ
            print(f"\n❌ Smart Money lỗi: {exc}")

        if not args.no_ai:
            if (AI_DIR / "data" / "vn100_list.csv").exists():
                print("\n== AI ==")
                ok = run_ai_step("run_daily_update.py")
                if ok and (AI_DIR / "models" / "lstm_return_model.keras").exists():
                    run_ai_step("predict_future.py", "--top", "5")
                elif ok:
                    print("ℹ️ Chưa có mô hình. Huấn luyện: python ai_stock/process_data_for_lstm.py && python ai_stock/train_lstm_model.py")
            else:
                print("\nℹ️ Bỏ qua AI (chưa có danh sách VN100). Khởi tạo: python ai_stock/get_stock_name.py")
        print(f"\n✅ Hoàn tất sau {time.time() - started:,.0f} giây")

    if args.serve or args.serve_only:
        serve(args.port)


if __name__ == "__main__":
    main()
