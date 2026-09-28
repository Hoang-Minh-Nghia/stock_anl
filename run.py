"""Chạy trên máy: cập nhật dữ liệu còn thiếu → phân tích → mở dashboard.

    python run.py              # cập nhật & phân tích
    python run.py --serve      # như trên, xong mở dashboard trên trình duyệt
    python run.py --serve-only # chỉ mở dashboard với dữ liệu đã có

Bản online chạy tự động trên GitHub Actions; script này chỉ dùng khi muốn chạy tay.
"""

import argparse
import functools
import http.server
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "anal_stock" / "public"


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
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not args.serve_only:
        started = time.time()
        from smart_money import pipeline

        try:
            pipeline.run()
        except Exception as exc:  # vẫn mở dashboard với dữ liệu cũ
            print(f"\n❌ Lỗi: {exc}")
        print(f"\n✅ Hoàn tất sau {time.time() - started:,.0f} giây")

    if args.serve or args.serve_only:
        serve(args.port)


if __name__ == "__main__":
    main()
