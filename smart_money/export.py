"""Lưu kết quả mỗi lần chạy thành file JSON cho dashboard cục bộ.

anal_stock/public/data/
    runs/YYYY-MM-DD.json   — đầy đủ: meta, stocks, flows của ngày đó
    index.json             — danh sách ngày đã có (dashboard dùng để chọn ngày)
    score_history.json     — điểm & hạng theo ngày (biểu đồ diễn biến)
"""

import json
import math

import numpy as np
import pandas as pd

from . import config

RUNS_DIR = config.PUBLIC_DATA_DIR / "runs"


def clean_value(value):
    """Chuyển giá trị pandas/numpy sang JSON hợp lệ (NaN/inf → null)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): clean_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_value(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(value) or math.isinf(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean_value(payload), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def write_run(run_date, meta, stocks, flows, overwrite=True):
    path = RUNS_DIR / f"{run_date}.json"
    if path.exists() and not overwrite:
        return path
    _write_json(path, {"meta": meta, "stocks": stocks, "flows": flows})
    return path


def rebuild_indexes():
    """Quét runs/*.json → index.json + score_history.json."""
    runs, history = {}, {}
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        date = path.stem
        meta = payload.get("meta") or {}
        stocks = payload.get("stocks") or {}
        runs[date] = {
            "model_version": meta.get("model_version"),
            "generated_at": meta.get("generated_at"),
            "legacy": bool(meta.get("legacy")),
            "tickers": len(stocks),
        }
        history[date] = {
            ticker: [row.get("Final_Score"), row.get("Xep_Hang"), row.get("Nhom_Chien_Luoc")]
            for ticker, row in stocks.items()
            if isinstance(row, dict) and row.get("Final_Score") is not None
        }
    dates = sorted(runs)
    _write_json(config.PUBLIC_DATA_DIR / "index.json", {"dates": dates, "latest": dates[-1] if dates else None, "runs": runs})
    _write_json(config.PUBLIC_DATA_DIR / "score_history.json", history)
    return dates
