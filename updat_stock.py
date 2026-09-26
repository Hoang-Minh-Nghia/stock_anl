"""Chỉ chạy phần Smart Money: `python updat_stock.py [--dry-run]`.

Chạy toàn bộ (Smart Money + AI + dashboard): `python run.py --serve`.
"""

from smart_money.pipeline import main

if __name__ == "__main__":
    main()
