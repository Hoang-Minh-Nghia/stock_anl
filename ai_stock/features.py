"""Hàm dùng chung cho pipeline AI: giá (kho cục bộ), chỉ báo kỹ thuật, bối cảnh thị trường, feature cho mô hình.

Tự tính chỉ báo bằng pandas (không phụ thuộc tên cột thay đổi theo phiên bản pandas_ta).
Mọi đường dẫn tính theo vị trí file → chạy script từ thư mục nào cũng được.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))

from market_data import price_store  # noqa: E402

DATA_DIR = BASE_DIR / "data"
STOCK_FILES_DIR = DATA_DIR / "stock_files"
MODEL_DATA_DIR = BASE_DIR / "model_data"
MODELS_DIR = BASE_DIR / "models"

PRICE_MASTER = DATA_DIR / "vn100_price_master.csv"
INDICATORS_FILE = DATA_DIR / "vn100_with_indicators.csv"
MACRO_FILE = DATA_DIR / "vn100_with_vietnam_macro.csv"
MARKET_CONTEXT_FILE = DATA_DIR / "market_context.csv"
VN100_LIST_FILE = DATA_DIR / "vn100_list.csv"

HISTORY_START = "2000-01-01"
MAX_DAILY_MOVE = 0.30  # |biến động 1 phiên| > 30% → nghi dữ liệu chưa điều chỉnh (chia tách/thưởng)

SECTOR_LEADERS = {
    "banking": ["VCB", "BID", "CTG", "TCB", "MBB"],
    "realestate": ["VHM", "VIC", "VRE", "NVL", "KDH"],
    "retail": ["MWG", "FRT", "PNJ", "MSN", "DGW"],
    "steel": ["HPG", "HSG", "NKG"],
    "securities": ["SSI", "VND", "VCI", "HCM", "SHS"],
}
CONTEXT_COLUMNS = ["vnindex_return"] + [f"{s}_return" for s in SECTOR_LEADERS]

# Feature dừng (stationary), không phụ thuộc mức giá → dùng chung một scaler cho mọi mã
MODEL_FEATURES = [
    "ret_1d", "ret_5d", "ret_20d", "log_volume_ratio", "rsi_n", "macd_n", "macd_hist_n",
    "bb_pct", "bb_width", "atr_n", "dist_sma20", "dist_sma50", "dist_sma200", "hl_range",
    "volatility_20d", "vnindex_ret_1d", "vnindex_ret_5d", "excess_ret_20d",
] + [f"{s}_return" for s in SECTOR_LEADERS]


def today_str():
    return pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").strftime("%Y-%m-%d")


# ---------------------------------------------------------------- prices
def load_prices(tickers, update=True):
    """Giá các mã từ kho cục bộ `data/prices/` (tự tải ngày còn thiếu nếu `update`).

    Trả (DataFrame dạng dài có cột ticker, thống kê cập nhật).
    """
    if update:
        frames, stats = price_store.update_many(tickers)
    else:
        frames, stats = {t: price_store.load(t) for t in tickers}, {}
    parts = []
    for ticker, df in frames.items():
        if df is not None and not df.empty:
            parts.append(df.assign(ticker=ticker))
    prices = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=price_store.COLUMNS + ["ticker"])
    return prices.sort_values(["ticker", "time"]).reset_index(drop=True), stats


# ---------------------------------------------------------------- indicators
def _rsi(close, length=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).where(loss != 0, 100.0)


def add_indicators(df):
    """Chỉ báo kỹ thuật cho MỘT mã (df đã sắp theo thời gian)."""
    df = df.sort_values("time").reset_index(drop=True).copy()
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"].astype(float)

    for n in (5, 10, 20, 50, 100, 200):
        df[f"sma_{n}"] = close.rolling(n).mean()
    df["ema_12"] = close.ewm(span=12, adjust=False, min_periods=12).mean()
    df["ema_26"] = close.ewm(span=26, adjust=False, min_periods=26).mean()
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["rsi_14"] = _rsi(close, 14)
    lowest, highest = low.rolling(14).min(), high.rolling(14).max()
    df["stoch_k"] = (100 * (close - lowest) / (highest - lowest).replace(0, np.nan)).rolling(3).mean()
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()
    df["roc_12"] = close.pct_change(12) * 100

    std20 = close.rolling(20).std(ddof=0)
    df["bb_mid"] = df["sma_20"]
    df["bb_upper"] = df["bb_mid"] + 2 * std20
    df["bb_lower"] = df["bb_mid"] - 2 * std20
    band = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["bb_width"] = band / df["bb_mid"]
    df["bb_pct"] = (close - df["bb_lower"]) / band

    prev_close = close.shift(1)
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    df["obv"] = (np.sign(close.diff()).fillna(0) * volume).cumsum()
    df["volume_sma_20"] = volume.rolling(20).mean()
    df["volume_ratio"] = volume / df["volume_sma_20"].replace(0, np.nan)

    df["high_low_ratio"] = (high - low) / close
    df["close_open_ratio"] = (close - df["open"]) / df["open"].replace(0, np.nan)
    df["daily_return"] = close.pct_change()
    df["volatility_20d"] = df["daily_return"].rolling(20).std()
    df["price_position_20d"] = (close - low.rolling(20).min()) / (high.rolling(20).max() - low.rolling(20).min()).replace(0, np.nan)
    return df


def compute_indicators(prices):
    frames = [add_indicators(g) for _, g in prices.groupby("ticker", sort=True)]
    return pd.concat(frames, ignore_index=True) if frames else prices


# ---------------------------------------------------------------- market context
def build_market_context(prices, update=True):
    """Lợi nhuận VNINDEX + lợi nhuận TB các mã đầu ngành theo ngày.

    Dùng giá có sẵn trong `prices`; VNINDEX và mã đầu ngành không thuộc VN100 lấy từ kho giá cục bộ.
    """
    have = set(prices["ticker"].unique())
    needed = {"VNINDEX"} | {t for tickers in SECTOR_LEADERS.values() for t in tickers}
    extra, _ = load_prices(sorted(needed - have), update=update)
    universe = pd.concat([prices[prices["ticker"].isin(needed)], extra], ignore_index=True)
    close = universe.pivot_table(index="time", columns="ticker", values="close").sort_index()
    returns = close.pct_change(fill_method=None)
    returns = returns.where(returns.abs() <= MAX_DAILY_MOVE)

    context = pd.DataFrame(index=close.index)
    context["vnindex_return"] = returns["VNINDEX"] if "VNINDEX" in returns else np.nan
    for sector, tickers in SECTOR_LEADERS.items():
        cols = [t for t in tickers if t in returns]
        # TB lợi nhuận (không phải TB giá) → không bị mã giá cao chi phối
        context[f"{sector}_return"] = returns[cols].mean(axis=1) if cols else np.nan
    context.index.name = "time"
    return context.reset_index()


def add_market_context(df, context):
    """Ghép bối cảnh theo ngày. Ngày thiếu dữ liệu → 0 (không dùng giá trị tương lai)."""
    df = df.drop(columns=[c for c in CONTEXT_COLUMNS if c in df.columns])
    merged = df.merge(context[["time"] + CONTEXT_COLUMNS], on="time", how="left")
    merged[CONTEXT_COLUMNS] = merged[CONTEXT_COLUMNS].fillna(0.0)
    return merged


# ---------------------------------------------------------------- model features
def build_model_features(df):
    """Feature dừng + cờ chất lượng dữ liệu cho TỪNG mã. df phải có chỉ báo + bối cảnh."""
    out = []
    for _, g in df.sort_values(["ticker", "time"]).groupby("ticker", sort=True):
        g = g.copy()
        close = g["close"]
        g["ret_1d"] = close.pct_change()
        g["ret_5d"] = close.pct_change(5)
        g["ret_20d"] = close.pct_change(20)
        g["log_volume_ratio"] = np.log(g["volume_ratio"].clip(lower=1e-3))
        g["rsi_n"] = g["rsi_14"] / 100 - 0.5
        g["macd_n"] = g["macd"] / close
        g["macd_hist_n"] = g["macd_hist"] / close
        g["atr_n"] = g["atr_14"] / close
        g["dist_sma20"] = close / g["sma_20"] - 1
        g["dist_sma50"] = close / g["sma_50"] - 1
        g["dist_sma200"] = close / g["sma_200"] - 1
        g["hl_range"] = g["high_low_ratio"]
        g["vnindex_ret_1d"] = g["vnindex_return"]
        log_vn = np.log1p(g["vnindex_return"])
        g["vnindex_ret_5d"] = np.expm1(log_vn.rolling(5).sum())
        vn20 = np.expm1(log_vn.rolling(20).sum())
        g["excess_ret_20d"] = g["ret_20d"] - vn20
        g["price_jump"] = g["ret_1d"].abs() > MAX_DAILY_MOVE
        out.append(g)
    result = pd.concat(out, ignore_index=True)
    result[MODEL_FEATURES] = result[MODEL_FEATURES].replace([np.inf, -np.inf], np.nan)
    return result
