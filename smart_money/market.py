"""Chỉ số giá / rủi ro / thanh khoản tính từ lịch sử giá ngày."""

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _period_return(close, window, skip=0):
    """Lợi nhuận từ `window` phiên trước đến `skip` phiên trước."""
    if len(close) <= window:
        return np.nan
    start = close.iloc[-(window + 1)]
    end = close.iloc[-(skip + 1)]
    if not (np.isfinite(start) and start > 0 and np.isfinite(end)):
        return np.nan
    return end / start - 1


def compute_price_metrics(history, benchmark=None):
    empty = {
        "Gia_SSI_Nghin": np.nan,
        "Ngay_Gia": None,
        "Ret_1M": np.nan,
        "Ret_3M": np.nan,
        "Ret_6M": np.nan,
        "Mom_6_1": np.nan,
        "Volatility_60D": np.nan,
        "Max_Drawdown_6M": np.nan,
        "Beta_120D": np.nan,
        "ADV_20D_VND": np.nan,
        "So_Phien_Gia": 0,
    }
    if history is None or history.empty:
        return empty

    close = history["close"].astype(float)
    ret = history["ret_1d"].astype(float)
    out = dict(empty)
    out["Gia_SSI_Nghin"] = float(close.iloc[-1])
    out["Ngay_Gia"] = history["date"].iloc[-1].strftime("%Y-%m-%d")
    out["So_Phien_Gia"] = int(len(close))
    out["Ret_1M"] = _period_return(close, 21)
    out["Ret_3M"] = _period_return(close, 63)
    out["Ret_6M"] = _period_return(close, 126)
    # Momentum 6-1: bỏ tháng gần nhất để tránh hiệu ứng đảo chiều ngắn hạn
    out["Mom_6_1"] = _period_return(close, 126, skip=21)

    tail_ret = ret.tail(60).dropna()
    if len(tail_ret) >= 40:
        out["Volatility_60D"] = float(tail_ret.std() * np.sqrt(TRADING_DAYS))

    window = close.tail(126).dropna()
    if len(window) >= 40:
        out["Max_Drawdown_6M"] = float((window / window.cummax() - 1).min())

    if "volume" in history:
        traded = (history["close"] * history["volume"] * 1000).tail(20).dropna()
        if len(traded) >= 10:
            out["ADV_20D_VND"] = float(traded.mean())

    if benchmark is not None and not benchmark.empty:
        merged = pd.merge(
            history[["date", "ret_1d"]], benchmark[["date", "ret_1d"]], on="date", suffixes=("_s", "_b")
        ).dropna().tail(120)
        if len(merged) >= 60:
            var_b = merged["ret_1d_b"].var()
            if var_b > 0:
                out["Beta_120D"] = float(merged["ret_1d_s"].cov(merged["ret_1d_b"]) / var_b)
    return out


def price_ratio_from_history(history, date0, date1):
    """Giá đóng cửa gần nhất ≤ date1 chia cho gần nhất ≤ date0."""
    if history is None or history.empty:
        return np.nan
    dates = history["date"]

    def close_at(when):
        when = pd.Timestamp(when).tz_localize(None) if pd.Timestamp(when).tzinfo else pd.Timestamp(when)
        mask = dates <= when
        if not mask.any():
            return np.nan
        return float(history.loc[mask, "close"].iloc[-1])

    c0, c1 = close_at(date0), close_at(date1)
    if not (np.isfinite(c0) and c0 > 0 and np.isfinite(c1)):
        return np.nan
    return c1 / c0
