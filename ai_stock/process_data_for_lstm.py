"""Bước 4: tạo dataset cho LSTM.

    python ai_stock/process_data_for_lstm.py [--horizon 5] [--lookback 30] [--val-start 2023-07-01] [--test-start 2024-07-01]

Khác bản cũ:
- Mục tiêu = lợi nhuận log N phiên tới (không phải giá tuyệt đối → tránh mô hình chỉ học "giá mai ≈ giá nay").
- Feature dừng, chuẩn hoá StandardScaler fit trên TRAIN.
- Chia Train / Validation / Test theo thời gian, bỏ (purge) N phiên ở ranh giới để không rò rỉ mục tiêu.
- Loại cửa sổ có biến động > 30%/phiên (dữ liệu chưa điều chỉnh chia tách).
- Lưu ma trận feature 2D float32 + chỉ số cửa sổ (không nhân bản dữ liệu → nhỏ hơn hàng chục lần).
"""

import argparse
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from features import MACRO_FILE, MODEL_DATA_DIR, MODEL_FEATURES, build_model_features

TRAIN_START = "2012-01-01"
CLIP = 5.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--train-start", default=TRAIN_START)
    parser.add_argument("--val-start", default="2023-07-01")
    parser.add_argument("--test-start", default="2024-07-01")
    args = parser.parse_args()
    H, L = args.horizon, args.lookback

    if not MACRO_FILE.exists():
        print(f"❌ Chưa có {MACRO_FILE}. Chạy run_daily_update.py hoặc các bước 1-3 trước.")
        return
    print("📂 Đọc dữ liệu...")
    raw = pd.read_csv(MACRO_FILE, parse_dates=["time"])
    raw = raw[raw["time"] >= pd.Timestamp(args.train_start) - pd.Timedelta(days=400)]  # dư cho SMA200
    df = build_model_features(raw).sort_values(["ticker", "time"]).reset_index(drop=True)

    tickers = df["ticker"].to_numpy()
    close = df["close"].to_numpy(dtype=float)
    feats = df[MODEL_FEATURES].to_numpy(dtype=np.float64)
    valid_row = np.isfinite(feats).all(axis=1) & ~df["price_jump"].to_numpy()

    # Mục tiêu: log(close[t+H] / close[t]) trong cùng mã
    same_ticker_ahead = np.zeros(len(df), dtype=bool)
    same_ticker_ahead[:-H] = tickers[H:] == tickers[:-H]
    target = np.full(len(df), np.nan)
    target[:-H] = np.log(close[H:] / close[:-H])
    target[~same_ticker_ahead] = np.nan
    # Không có cú nhảy giá trong khoảng mục tiêu
    jump = df["price_jump"].to_numpy().astype(int)
    jump_ahead = np.zeros(len(df), dtype=int)
    csum = np.concatenate([[0], np.cumsum(jump)])
    jump_ahead[:-H] = csum[H + 1:] - csum[1:len(df) - H + 1]
    target[jump_ahead > 0] = np.nan

    # Cửa sổ hợp lệ: L dòng liên tiếp cùng mã, đều hợp lệ
    csum_valid = np.concatenate([[0], np.cumsum(valid_row.astype(int))])
    end_idx = np.arange(L - 1, len(df))
    window_ok = (csum_valid[end_idx + 1] - csum_valid[end_idx + 1 - L]) == L
    window_ok &= tickers[end_idx] == tickers[end_idx - (L - 1)]
    sample_end = end_idx[window_ok & np.isfinite(target[end_idx])]

    dates = df["time"].to_numpy()[sample_end]
    trading_days = np.sort(df["time"].unique())

    def purge_before(boundary):
        """Ngày giao dịch cách ranh giới < H phiên (mục tiêu sẽ chồng sang tập sau)."""
        pos = np.searchsorted(trading_days, np.datetime64(pd.Timestamp(boundary)))
        return trading_days[max(0, pos - H)]

    train_start = np.datetime64(pd.Timestamp(args.train_start))
    val_start, test_start = np.datetime64(pd.Timestamp(args.val_start)), np.datetime64(pd.Timestamp(args.test_start))
    split = np.full(len(sample_end), "", dtype=object)
    split[(dates >= train_start) & (dates < purge_before(args.val_start))] = "train"
    split[(dates >= val_start) & (dates < purge_before(args.test_start))] = "val"
    split[dates >= test_start] = "test"

    # Scaler fit trên các dòng thuộc giai đoạn train
    train_rows = valid_row & (df["time"].to_numpy() < val_start) & (df["time"].to_numpy() >= train_start)
    scaler = StandardScaler().fit(feats[train_rows])
    scaled = np.clip(scaler.transform(np.where(np.isfinite(feats), feats, 0.0)), -CLIP, CLIP).astype(np.float32)

    y = target[sample_end]
    y_train = y[split == "train"]
    target_std = float(np.std(y_train))

    MODEL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        MODEL_DATA_DIR / "dataset.npz",
        X=scaled,
        sample_end=sample_end.astype(np.int64),
        y=y.astype(np.float32),
        dates=dates.astype("datetime64[D]").astype(np.int64),
        ticker=tickers[sample_end].astype(str),
        split=split.astype(str),
        # Baseline tham chiếu (giá trị gốc, chưa chuẩn hoá)
        baseline_mom20=df["ret_20d"].to_numpy()[sample_end].astype(np.float32),
        baseline_rev5=(-df["ret_5d"].to_numpy()[sample_end]).astype(np.float32),
        baseline_lowvol=(-df["volatility_20d"].to_numpy()[sample_end]).astype(np.float32),
    )
    joblib.dump(scaler, MODEL_DATA_DIR / "feature_scaler_v2.pkl")
    meta = {
        "features": MODEL_FEATURES,
        "lookback": L,
        "horizon": H,
        "target": f"log_return_{H}d",
        "target_std": target_std,
        "clip": CLIP,
        "train_start": args.train_start,
        "val_start": args.val_start,
        "test_start": args.test_start,
        "counts": {s: int((split == s).sum()) for s in ("train", "val", "test")},
        "data_end": str(df["time"].max().date()),
    }
    (MODEL_DATA_DIR / "dataset_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Feature {len(MODEL_FEATURES)} · lookback {L} · horizon {H} phiên")
    print(f"   Train {meta['counts']['train']:,} · Val {meta['counts']['val']:,} · Test {meta['counts']['test']:,} mẫu")
    print(f"   Lưu: {MODEL_DATA_DIR / 'dataset.npz'} ({(MODEL_DATA_DIR / 'dataset.npz').stat().st_size / 1e6:,.0f} MB)")
    old = [p for p in MODEL_DATA_DIR.glob("X_*.npy")]
    if old:
        print(f"ℹ️ File định dạng cũ không còn dùng (có thể xoá để giải phóng {sum(p.stat().st_size for p in old) / 1e9:.1f} GB): {', '.join(p.name for p in old)}")


if __name__ == "__main__":
    main()
