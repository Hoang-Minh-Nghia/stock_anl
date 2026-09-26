"""Bước 6: dự báo lợi nhuận N phiên tới cho toàn bộ mã, xếp hạng.

    python ai_stock/predict_future.py [--ticker HPG]

Kết quả: models/predictions_latest.csv. Nếu mô hình không vượt baseline trên tập test,
kết quả được đánh dấu "chỉ tham khảo".
"""

import argparse
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import joblib
import numpy as np
import pandas as pd

from features import MACRO_FILE, MODEL_DATA_DIR, MODELS_DIR, build_model_features, today_str


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Chỉ in chi tiết một mã")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    meta_path = MODEL_DATA_DIR / "dataset_meta.json"
    model_path = MODELS_DIR / "lstm_return_model.keras"
    if not (meta_path.exists() and model_path.exists()):
        print("❌ Chưa có mô hình. Chạy process_data_for_lstm.py và train_lstm_model.py trước.")
        return

    import tensorflow as tf

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    metrics = json.loads((MODELS_DIR / "metrics.json").read_text(encoding="utf-8")) if (MODELS_DIR / "metrics.json").exists() else {}
    scaler = joblib.load(MODEL_DATA_DIR / "feature_scaler_v2.pkl")
    model = tf.keras.models.load_model(model_path)
    L, H, features, std = meta["lookback"], meta["horizon"], meta["features"], meta["target_std"]

    raw = pd.read_csv(MACRO_FILE, parse_dates=["time"])
    raw = raw[raw["time"] >= raw["time"].max() - pd.Timedelta(days=500)]
    df = build_model_features(raw)

    windows, rows = [], []
    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("time").tail(L)
        values = g[features].to_numpy(dtype=float)
        if len(g) < L or not np.isfinite(values).all() or g["price_jump"].any():
            continue
        windows.append(np.clip(scaler.transform(values), -meta["clip"], meta["clip"]))
        rows.append({"ticker": ticker, "last_date": g["time"].iloc[-1], "close": g["close"].iloc[-1]})

    if not windows:
        print("❌ Không có mã nào đủ dữ liệu.")
        return
    pred = model.predict(np.stack(windows).astype(np.float32), verbose=0).ravel() * std
    result = pd.DataFrame(rows)
    result["pred_log_return"] = pred
    result[f"du_bao_{H}_phien_pct"] = np.expm1(pred) * 100
    result["xep_hang"] = result["pred_log_return"].rank(ascending=False, method="min").astype(int)
    result["nhom"] = pd.qcut(result["pred_log_return"].rank(method="first"), 5, labels=["Thấp nhất", "Thấp", "Giữa", "Cao", "Cao nhất"])
    result = result.sort_values("xep_hang")
    result.to_csv(MODELS_DIR / "predictions_latest.csv", index=False, encoding="utf-8-sig")

    last = result["last_date"].max()
    age = (pd.Timestamp(today_str()) - last).days
    print(f"📅 Dữ liệu tới {last:%Y-%m-%d}" + (f" · ⚠️ đã cũ {age} ngày, chạy run_daily_update.py" if age > 3 else ""))
    test = metrics.get("splits", {}).get("test", {}).get("model", {})
    if metrics:
        print(f"📊 Chất lượng mô hình trên test: IC {test.get('ic_mean', float('nan')):+.4f} (t={test.get('ic_tstat', float('nan')):+.2f}), đúng hướng {test.get('hit_rate', float('nan')):.1%}")
    if not metrics.get("useful", False):
        print("⚠️ MÔ HÌNH CHƯA VƯỢT BASELINE — kết quả dưới đây CHỈ ĐỂ THAM KHẢO, không dùng làm tín hiệu giao dịch.")
        for reason in metrics.get("not_useful_reasons", []):
            print(f"   - {reason}")

    cols = ["xep_hang", "ticker", "close", f"du_bao_{H}_phien_pct", "nhom"]
    with pd.option_context("display.float_format", "{:,.2f}".format, "display.width", 120):
        if args.ticker:
            print(result[result["ticker"] == args.ticker.upper()][cols].to_string(index=False))
        else:
            print(f"\nTop {args.top} dự báo lợi nhuận {H} phiên cao nhất:")
            print(result[cols].head(args.top).to_string(index=False))
            print(f"\nTop {args.top} thấp nhất:")
            print(result[cols].tail(args.top).iloc[::-1].to_string(index=False))
    print(f"\n💾 {MODELS_DIR / 'predictions_latest.csv'} ({len(result)} mã)")


if __name__ == "__main__":
    main()
