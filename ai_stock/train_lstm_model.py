"""Bước 5: huấn luyện LSTM dự báo lợi nhuận N phiên và đánh giá so với baseline.

    python ai_stock/train_lstm_model.py [--epochs 30] [--max-train-samples 300000]

EarlyStopping theo tập VALIDATION; tập TEST chỉ dùng một lần để báo cáo cuối.
Kết quả: models/lstm_return_model.keras, models/metrics.json, models/training_loss.png
"""

import argparse
import json
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf

from evaluation import evaluate_predictions, model_is_useful
from features import MODEL_DATA_DIR, MODELS_DIR


def make_dataset(X, sample_end, y, lookback, batch_size, shuffle, seed=42):
    X_const = tf.constant(X)
    offsets = tf.range(-lookback + 1, 1, dtype=tf.int64)
    ds = tf.data.Dataset.from_tensor_slices((sample_end.astype(np.int64), y.astype(np.float32)))
    if shuffle:
        ds = ds.shuffle(min(len(sample_end), 200_000), seed=seed, reshuffle_each_iteration=True)
    ds = ds.batch(batch_size)
    ds = ds.map(lambda idx, target: (tf.gather(X_const, idx[:, None] + offsets[None, :]), target), num_parallel_calls=tf.data.AUTOTUNE)
    return ds.prefetch(tf.data.AUTOTUNE)


def build_model(lookback, n_features, units=32, dropout=0.2):
    inputs = tf.keras.Input(shape=(lookback, n_features))
    x = tf.keras.layers.LSTM(units)(inputs)
    x = tf.keras.layers.Dropout(dropout)(x)
    x = tf.keras.layers.Dense(16, activation="relu")(x)
    outputs = tf.keras.layers.Dense(1)(x)
    model = tf.keras.Model(inputs, outputs)
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss=tf.keras.losses.Huber(delta=1.0))
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--units", type=int, default=32)
    parser.add_argument("--max-train-samples", type=int, default=0, help="Lấy mẫu ngẫu nhiên để train nhanh (0 = tất cả)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    tf.keras.utils.set_random_seed(args.seed)

    meta_path = MODEL_DATA_DIR / "dataset_meta.json"
    if not meta_path.exists():
        print("❌ Chưa có dataset. Chạy process_data_for_lstm.py trước.")
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    data = np.load(MODEL_DATA_DIR / "dataset.npz")
    X, sample_end, y, split = data["X"], data["sample_end"], data["y"], data["split"]
    dates = data["dates"].astype("datetime64[D]")
    L, H, std = meta["lookback"], meta["horizon"], meta["target_std"]

    idx = {s: np.where(split == s)[0] for s in ("train", "val", "test")}
    if args.max_train_samples and len(idx["train"]) > args.max_train_samples:
        rng = np.random.default_rng(args.seed)
        idx["train"] = np.sort(rng.choice(idx["train"], args.max_train_samples, replace=False))
    print(f"📂 Train {len(idx['train']):,} · Val {len(idx['val']):,} · Test {len(idx['test']):,} · {X.shape[1]} feature · lookback {L} · horizon {H}")

    # Chuẩn hoá mục tiêu theo độ lệch chuẩn train (Huber loss ổn định hơn)
    train_ds = make_dataset(X, sample_end[idx["train"]], y[idx["train"]] / std, L, args.batch_size, shuffle=True, seed=args.seed)
    val_ds = make_dataset(X, sample_end[idx["val"]], y[idx["val"]] / std, L, args.batch_size * 2, shuffle=False)

    model = build_model(L, X.shape[1], units=args.units)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "lstm_return_model.keras"
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=2, min_lr=1e-5),
        tf.keras.callbacks.ModelCheckpoint(model_path, monitor="val_loss", save_best_only=True),
    ]
    history = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs, callbacks=callbacks, verbose=2)

    def predict(split_name):
        ds = make_dataset(X, sample_end[idx[split_name]], y[idx[split_name]], L, args.batch_size * 2, shuffle=False)
        return model.predict(ds, verbose=0).ravel() * std

    report = {"dataset": meta, "epochs_trained": len(history.history["loss"]), "splits": {}}
    for split_name in ("val", "test"):
        pred = predict(split_name)
        rows = idx[split_name]
        report["splits"][split_name] = {
            "model": evaluate_predictions(pred, y[rows], dates[rows], H),
            "baselines": {
                name: evaluate_predictions(data[key][rows], y[rows], dates[rows], H)
                for name, key in (("momentum_20d", "baseline_mom20"), ("reversal_5d", "baseline_rev5"), ("low_volatility", "baseline_lowvol"))
            },
        }

    test = report["splits"]["test"]
    useful, reasons = model_is_useful(test["model"], test["baselines"])
    report["useful"] = useful
    report["not_useful_reasons"] = reasons
    (MODELS_DIR / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=float), encoding="utf-8")

    plt.figure(figsize=(9, 5))
    plt.plot(history.history["loss"], label="Train")
    plt.plot(history.history["val_loss"], label="Validation")
    plt.title("Huber loss (lợi nhuận chuẩn hoá)")
    plt.xlabel("Epoch")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.savefig(MODELS_DIR / "training_loss.png", dpi=120, bbox_inches="tight")

    def row(name, m):
        return f"  {name:<16} IC {m.get('ic_mean', float('nan')):+.4f} (t={m.get('ic_tstat', float('nan')):+.2f}) · đúng hướng {m.get('hit_rate', float('nan')):.1%} · top-bottom {m.get('top_bottom_spread', float('nan')):+.2%} · RMSE vs 0: {m.get('rmse_improvement_pct', float('nan')):+.2f}%"

    for split_name in ("val", "test"):
        s = report["splits"][split_name]
        print(f"\n📊 {split_name.upper()}:")
        print(row("LSTM", s["model"]))
        for name, m in s["baselines"].items():
            print(row(name, m))
    print("\n" + ("✅ Mô hình vượt baseline trên tập test." if useful else "⚠️ Mô hình CHƯA đủ tốt để tham khảo: " + "; ".join(reasons)))
    print(f"💾 {model_path} · {MODELS_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
