import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ai_stock"))

from evaluation import evaluate_predictions, model_is_useful  # noqa: E402
from features import CONTEXT_COLUMNS, MODEL_FEATURES, add_indicators, add_market_context, build_model_features  # noqa: E402


def fake_prices(n=320, ticker="AAA", seed=0):
    rng = np.random.default_rng(seed)
    close = 20 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame(
        {
            "time": pd.bdate_range("2020-01-01", periods=n),
            "open": close * (1 + rng.normal(0, 0.005, n)),
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": rng.integers(100_000, 1_000_000, n),
            "ticker": ticker,
        }
    )


def with_context(df):
    ctx = pd.DataFrame({"time": df["time"].unique()})
    for col in CONTEXT_COLUMNS:
        ctx[col] = 0.001
    return add_market_context(add_indicators(df), ctx)


def test_indicator_ranges():
    ind = add_indicators(fake_prices())
    rsi = ind["rsi_14"].dropna()
    assert rsi.between(0, 100).all()
    assert (ind["bb_upper"].dropna() >= ind["bb_lower"].dropna()).all()
    assert (ind["atr_14"].dropna() > 0).all()


def test_features_have_no_lookahead():
    """Thay đổi dữ liệu TƯƠNG LAI không được làm đổi feature ở quá khứ."""
    base = fake_prices()
    altered = base.copy()
    altered.loc[altered.index[-20:], ["close", "high", "low", "open"]] *= 1.5
    f1 = build_model_features(with_context(base)).set_index("time")[MODEL_FEATURES]
    f2 = build_model_features(with_context(altered)).set_index("time")[MODEL_FEATURES]
    cutoff = base["time"].iloc[-21]
    pd.testing.assert_frame_equal(f1.loc[:cutoff], f2.loc[:cutoff])


def test_price_jump_flag():
    df = fake_prices()
    df.loc[200:, ["open", "high", "low", "close"]] *= 0.5  # chia tách chưa điều chỉnh
    feats = build_model_features(with_context(df))
    assert feats["price_jump"].sum() == 1


def test_evaluation_detects_signal_and_noise():
    rng = np.random.default_rng(1)
    dates = np.repeat(pd.bdate_range("2024-01-01", periods=120), 50)
    actual = rng.normal(0, 0.03, len(dates))
    good = evaluate_predictions(actual + rng.normal(0, 0.03, len(dates)), actual, dates, horizon=5)
    noise = evaluate_predictions(rng.normal(0, 0.03, len(dates)), actual, dates, horizon=5)
    assert good["ic_mean"] > 0.5 and good["ic_tstat"] > 2
    assert abs(noise["ic_mean"]) < 0.05
    useful, _ = model_is_useful(good, {"baseline": noise})
    not_useful, reasons = model_is_useful(noise, {"baseline": good})
    assert useful and not not_useful and reasons
