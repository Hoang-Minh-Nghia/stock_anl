"""Kiểm chứng sức dự báo của điểm số (dùng dữ liệu trên máy).

    python -m tools.evaluate_scores                                 # điểm đã lưu mỗi ngày
    python -m tools.evaluate_scores --price-factors [--years 14]    # nhân tố giá trên kho giá cục bộ

Chỉ số:
- IC (Information Coefficient): tương quan hạng Spearman giữa điểm hôm nay và lợi nhuận N phiên sau,
  tính theo từng ngày rồi lấy trung bình. IC > 0.03 và t-stat > 2 được coi là có ý nghĩa.
- Top-Bottom: lợi nhuận TB nhóm 20% điểm cao nhất trừ nhóm 20% thấp nhất.

Lưu ý: kết quả quá khứ không đảm bảo tương lai; danh sách mã hiện tại có survivorship bias.
"""

import argparse
import io
import json
import sys

import numpy as np
import pandas as pd

from market_data import price_store
from smart_money import config


def load_close(tickers):
    frames, _ = price_store.update_many(tickers)
    closes = {t: df.set_index("time")["close"] for t, df in frames.items() if df is not None}
    return pd.DataFrame(closes).sort_index()


def information_coefficient(scores, fwd, step):
    """scores/fwd: DataFrame ngày × mã. Dùng các ngày cách nhau `step` phiên để tránh chồng lấn."""
    dates = [d for d in scores.index if d in fwd.index][::step]
    ics, spreads = [], []
    for d in dates:
        s, r = scores.loc[d], fwd.loc[d]
        valid = s.notna() & r.notna()
        if valid.sum() < 15:
            continue
        s, r = s[valid], r[valid]
        ics.append(s.rank().corr(r.rank()))
        q = s.rank(pct=True)
        spreads.append(r[q >= 0.8].mean() - r[q <= 0.2].mean())
    ics, spreads = pd.Series(ics, dtype=float), pd.Series(spreads, dtype=float)
    n = len(ics)
    return {
        "so_ky": n,
        "IC_TB": ics.mean() if n else np.nan,
        "IC_tstat": ics.mean() / ics.std() * np.sqrt(n) if n > 2 and ics.std() > 0 else np.nan,
        "Ty_Le_IC_Duong": (ics > 0).mean() if n else np.nan,
        "TopBottom_TB": spreads.mean() if n else np.nan,
    }


def evaluate_saved_scores(horizon):
    path = config.PUBLIC_DATA_DIR / "score_history.json"
    if not path.exists():
        print("Chưa có lịch sử điểm. Chạy `python run.py` trước.")
        return
    history = json.loads(path.read_text(encoding="utf-8"))
    runs = json.loads((config.PUBLIC_DATA_DIR / "index.json").read_text(encoding="utf-8")).get("runs", {})
    records = [
        {"date": pd.Timestamp(date), "ticker": t, "score": v[0], "model": runs.get(date, {}).get("model_version") or "v3"}
        for date, rows in history.items()
        for t, v in rows.items()
    ]
    df = pd.DataFrame(records)
    close = load_close(df["ticker"].unique())
    fwd = close.shift(-horizon) / close - 1
    rows = {}
    for model, group in df.groupby("model"):
        scores = group.pivot_table(index="date", columns="ticker", values="score")
        rows[f"{model} ({len(scores)} ngày)"] = information_coefficient(scores, fwd, step=horizon)
    print(f"Điểm đã lưu, lợi nhuận {horizon} phiên sau:")
    print(pd.DataFrame(rows).T.to_string(float_format=lambda v: f"{v:,.4f}"))


def evaluate_price_factors(horizon, years):
    latest = sorted(config.SNAPSHOT_DIR.glob("*.csv"))[-1]
    tickers = sorted(pd.read_csv(latest)["Ma_Co_Phieu"].dropna().unique())
    tickers = [t for t in tickers if not str(t).startswith(config.ETF_PREFIXES)]
    close = load_close(tickers)
    close = close[close.index >= pd.Timestamp.now() - pd.DateOffset(years=years)]
    fwd = close.shift(-horizon) / close - 1
    ret = close.pct_change(fill_method=None)
    factors = {
        "Mom_6_1": close.shift(21) / close.shift(126) - 1,
        "Ret_3M": close / close.shift(63) - 1,
        "Ret_1M": close / close.shift(21) - 1,
        "Low_Vol_60D": -ret.rolling(60).std(),
        "Low_Drawdown_6M": close / close.rolling(126).max() - 1,
    }
    print(f"Nhân tố giá: {len(close.columns)} mã, {years} năm, lợi nhuận {horizon} phiên sau")
    rows = {name: information_coefficient(f.iloc[126:], fwd, step=horizon) for name, f in factors.items()}
    print(pd.DataFrame(rows).T.to_string(float_format=lambda v: f"{v:,.4f}"))


def main():
    if (sys.stdout.encoding or "").lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--price-factors", action="store_true")
    parser.add_argument("--years", type=int, default=3)
    args = parser.parse_args()
    if args.price_factors:
        evaluate_price_factors(args.horizon, args.years)
    else:
        evaluate_saved_scores(args.horizon)


if __name__ == "__main__":
    main()
