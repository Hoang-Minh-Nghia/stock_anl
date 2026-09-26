"""(Chạy 1 lần) Chuyển lịch sử điểm số từ Firebase `stocks/{ngày}` về máy.

    python _archive/firebase/import_firebase_history.py

Ghi vào anal_stock/public/data/runs/{ngày}.json (dạng mô hình cũ v3). Không ghi đè ngày đã có trên máy.
Chỉ đọc Firebase, không xoá/sửa gì trên đó.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from smart_money import export  # noqa: E402

DB_URL = "https://stock-trading-ad193-default-rtdb.asia-southeast1.firebasedatabase.app"


def get(path, params=None, retries=4):
    for attempt in range(retries):
        try:
            resp = requests.get(f"{DB_URL}/{path}.json", params=params, timeout=120)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        print(f"   thử lại {path} ({attempt + 1})")
    return None


def import_date(date):
    target = export.RUNS_DIR / f"{date}.json"
    if target.exists():
        return date, "đã có"
    records = get(f"stocks/{date}")
    if not isinstance(records, dict) or not records:
        return date, "lỗi"
    meta = {"run_date": date, "model_version": "v3-firebase", "legacy": True, "imported_from": "firebase"}
    export.write_run(date, meta, records, [], overwrite=False)
    return date, "OK"


def main():
    keys = get("stocks", params={"shallow": "true"}) or {}
    dates = sorted(keys)
    print(f"Firebase có {len(dates)} ngày điểm số")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(import_date, dates))
    summary = {}
    for date, status in results:
        summary.setdefault(status, []).append(date)
    for status, items in summary.items():
        print(f"  {status}: {len(items)}" + (f" ({', '.join(items[:5])}...)" if status == "lỗi" else ""))
    print(f"Tổng số ngày trên máy: {len(export.rebuild_indexes())}")


if __name__ == "__main__":
    main()
