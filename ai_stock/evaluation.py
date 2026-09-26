"""Chỉ số đánh giá mô hình dự báo lợi nhuận (dùng chung cho train và predict)."""

import numpy as np
import pandas as pd


def evaluate_predictions(pred, actual, dates, horizon):
    """pred/actual: lợi nhuận log N phiên; dates: ngày của mẫu.

    - RMSE mô hình vs baseline dự báo 0
    - Tỷ lệ đúng hướng (bỏ mẫu |thực tế| rất nhỏ)
    - IC theo ngày: tương quan hạng Spearman giữa dự báo và thực tế trên các mã cùng ngày
    - Top-Bottom: lợi nhuận TB nhóm 20% dự báo cao nhất − 20% thấp nhất (các ngày cách nhau N phiên)
    """
    df = pd.DataFrame({"pred": np.asarray(pred, dtype=float), "actual": np.asarray(actual, dtype=float), "date": pd.to_datetime(dates)})
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    if df.empty:
        return {}

    rmse = float(np.sqrt(np.mean((df["pred"] - df["actual"]) ** 2)))
    rmse_zero = float(np.sqrt(np.mean(df["actual"] ** 2)))
    moving = df[df["actual"].abs() > 1e-3]
    hit_rate = float((np.sign(moving["pred"]) == np.sign(moving["actual"])).mean()) if len(moving) else np.nan
    base_up_rate = float((moving["actual"] > 0).mean()) if len(moving) else np.nan

    ics, spreads = [], []
    unique_dates = np.sort(df["date"].unique())
    step_dates = set(pd.to_datetime(unique_dates[::max(1, horizon)]))
    for date, g in df.groupby("date"):
        if len(g) < 20:
            continue
        ic = g["pred"].rank().corr(g["actual"].rank())
        if np.isfinite(ic):
            ics.append(ic)
        if date in step_dates:
            q = g["pred"].rank(pct=True)
            spreads.append(g.loc[q >= 0.8, "actual"].mean() - g.loc[q <= 0.2, "actual"].mean())

    ics = np.array(ics)
    n_independent = max(1, len(ics) // max(1, horizon))
    ic_mean = float(ics.mean()) if len(ics) else np.nan
    ic_std = float(ics.std()) if len(ics) > 1 else np.nan
    return {
        "n_samples": int(len(df)),
        "n_days": int(len(ics)),
        "rmse": rmse,
        "rmse_zero_baseline": rmse_zero,
        "rmse_improvement_pct": float((1 - rmse / rmse_zero) * 100) if rmse_zero > 0 else np.nan,
        "hit_rate": hit_rate,
        "up_rate_baseline": base_up_rate,
        "ic_mean": ic_mean,
        # t-stat hiệu chỉnh chồng lấn: dùng số kỳ độc lập ≈ số ngày / horizon
        "ic_tstat": float(ic_mean / ic_std * np.sqrt(n_independent)) if ic_std and ic_std > 0 else np.nan,
        "ic_positive_rate": float((ics > 0).mean()) if len(ics) else np.nan,
        "top_bottom_spread": float(np.mean(spreads)) if spreads else np.nan,
    }


def model_is_useful(test_metrics, baseline_metrics, min_ic=0.02, min_tstat=2.0):
    """Mô hình chỉ đáng tham khảo khi IC dương có ý nghĩa và vượt baseline tốt nhất."""
    ic = test_metrics.get("ic_mean", np.nan)
    tstat = test_metrics.get("ic_tstat", np.nan)
    best_baseline = max([m.get("ic_mean", -np.inf) for m in baseline_metrics.values()] + [-np.inf])
    reasons = []
    if not np.isfinite(ic) or ic < min_ic:
        reasons.append(f"IC test {ic:.3f} < {min_ic}")
    if not np.isfinite(tstat) or tstat < min_tstat:
        reasons.append(f"t-stat {tstat:.2f} < {min_tstat}")
    if np.isfinite(ic) and ic <= best_baseline:
        reasons.append(f"không vượt baseline tốt nhất (IC {best_baseline:.3f})")
    return len(reasons) == 0, reasons
