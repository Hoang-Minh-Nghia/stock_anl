"""Lưu / đọc snapshot danh mục quỹ trên máy (`data/smart_money_snapshots/`)."""

import datetime as dt

import pandas as pd

from . import config


def _stamp_from_path(path):
    for fmt in ("%Y-%m-%d_%H%M%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(path.stem, fmt)
        except ValueError:
            continue
    return None


def save_snapshot(df, run_date):
    """Một file mỗi ngày (`YYYY-MM-DD.csv`); chạy lại trong ngày sẽ ghi đè."""
    config.SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SNAPSHOT_DIR / f"{run_date}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_local_history(before_date=None):
    """Đọc các snapshot (bỏ các snapshot của ngày `before_date` trở về sau)."""
    if not config.SNAPSHOT_DIR.exists():
        return pd.DataFrame()
    frames = []
    for path in sorted(config.SNAPSHOT_DIR.glob("*.csv")):
        if _stamp_from_path(path) is None:
            continue
        if before_date and path.stem[:10] >= before_date:
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if frame.empty:
            continue
        frame["Snapshot_Stamp"] = path.stem
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def carry_forward_failed_funds(current, history, failed):
    """Quỹ lỗi mạng ở lần chạy này → dùng lại danh mục gần nhất (không coi là bán hết)."""
    if not failed or history.empty:
        return current, []
    failed_names = {f["name"] for f in failed if f.get("name")}
    latest_stamp_by_fund = history.groupby("Ten_Quy")["Snapshot_Stamp"].max()
    carried_rows, carried_funds = [], []
    for fund in sorted(failed_names):
        if fund not in latest_stamp_by_fund.index:
            continue
        rows = history[(history["Ten_Quy"] == fund) & (history["Snapshot_Stamp"] == latest_stamp_by_fund[fund])].copy()
        if rows.empty:
            continue
        if not current.empty:
            rows["Snapshot_Stamp"] = current["Snapshot_Stamp"].iloc[0]
            rows["Snapshot_Date"] = current["Snapshot_Date"].iloc[0]
        rows["Fetch_Status"] = "CARRIED"
        carried_rows.append(rows)
        carried_funds.append(fund)
    if not carried_rows:
        return current, []
    merged = pd.concat([current] + carried_rows, ignore_index=True)
    return merged, carried_funds
