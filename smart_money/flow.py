"""Tính dòng tiền quỹ giữa hai kỳ báo cáo danh mục.

Vì sao không so sánh ngày-với-ngày: FMarket chỉ cập nhật danh mục theo kỳ báo cáo (thường
hàng tháng), nên snapshot các ngày trong cùng kỳ giống hệt nhau. Mỗi quỹ được chia thành các
"kỳ" (chuỗi snapshot liên tiếp có cùng danh mục); dòng tiền = kỳ hiện tại so với kỳ liền trước.

Cách định giá dòng tiền (ưu tiên từ trên xuống):
1. Có số cổ phiếu (`So_Co_Phieu`) cả hai kỳ → (CP kỳ này − CP kỳ trước) × giá/CP kỳ này.
   Loại bỏ hoàn toàn ảnh hưởng tăng/giảm giá. Có phát hiện chia tách/thưởng cổ phiếu.
2. Snapshot cũ không có số CP → giá trị kỳ này − giá trị kỳ trước × (giá hiện tại / giá kỳ trước).

Giới hạn Top 10: FMarket chỉ công bố 10 mã lớn nhất. Mã biến mất khỏi danh sách đầy đủ 10 mã
có thể vẫn được giữ với tỷ trọng nhỏ hơn mã thứ 10 → dùng tỷ trọng mã thứ 10 làm cận trên,
nên dòng tiền bán/mua được ước lượng thận trọng (không còn "bán hết" giả).
"""

import numpy as np
import pandas as pd

from . import config

BUY_STATUSES = {"INCREASE", "NEW_BUY", "ENTER_TOP10"}
SELL_STATUSES = {"DECREASE", "EXIT", "LEFT_TOP10"}
STALE_PERIOD_DAYS = 75


def _period_signature(rows):
    items = tuple(sorted((str(t), round(float(p), 2)) for t, p in zip(rows["Ma_Co_Phieu"], rows["Ty_Le_Trong_Quy"])))
    aum = round(float(rows["AUM_VND"].iloc[0]) / 1e6) if "AUM_VND" in rows and len(rows) else 0
    return items, aum


def build_fund_periods(history):
    """{fund: [period, ...]} theo thứ tự thời gian. Mỗi period là dict."""
    if history.empty:
        return {}
    history = history.copy()
    history["Ma_Co_Phieu"] = history["Ma_Co_Phieu"].astype(str).str.strip().str.upper()
    periods = {}
    for fund, fund_rows in history.groupby("Ten_Quy", sort=False):
        fund_periods = []
        for stamp, rows in sorted(fund_rows.groupby("Snapshot_Stamp"), key=lambda item: item[0]):
            rows = rows.drop_duplicates("Ma_Co_Phieu", keep="first")
            signature = _period_signature(rows)
            snap_date = pd.to_datetime(str(stamp)[:10])
            report_date = None
            if "Report_Date" in rows and rows["Report_Date"].notna().any():
                report_date = pd.to_datetime(rows["Report_Date"].dropna().iloc[0])
            if fund_periods and fund_periods[-1]["signature"] == signature:
                period = fund_periods[-1]
                period["last_stamp"] = stamp
                if period["report_date"] is None and report_date is not None:
                    period["report_date"] = report_date
                # Ưu tiên bản ghi mới nhất (có đủ cột volume / report date)
                if "So_Co_Phieu" in rows and rows["So_Co_Phieu"].notna().any():
                    period["rows"] = rows.set_index("Ma_Co_Phieu")
                continue
            fund_periods.append(
                {
                    "fund": fund,
                    "signature": signature,
                    "first_stamp": stamp,
                    "first_date": snap_date,
                    "last_stamp": stamp,
                    "report_date": report_date,
                    "rows": rows.set_index("Ma_Co_Phieu"),
                }
            )
        for period in fund_periods:
            period["last_date"] = pd.to_datetime(str(period["last_stamp"])[:10])
        periods[fund] = fund_periods
    _estimate_missing_report_dates(periods)
    return periods


def _estimate_missing_report_dates(periods):
    """Snapshot cũ không có ngày báo cáo → ước lượng = ngày xuất hiện − độ trễ công bố điển hình.

    Cần để kỳ cũ và kỳ mới dùng cùng hệ mốc thời gian khi điều chỉnh theo giá.
    """
    lags = [
        (p["first_date"] - p["report_date"]).days
        for fund_periods in periods.values()
        for p in fund_periods
        if p["report_date"] is not None and (p["first_date"] - p["report_date"]).days >= 0
    ]
    lag = int(np.median(lags)) if lags else 0
    for fund_periods in periods.values():
        for p in fund_periods:
            p["report_date_estimated"] = p["report_date"] is None
            if p["report_date"] is None:
                p["report_date"] = p["first_date"] - pd.Timedelta(days=lag)


def _pick_previous_period(fund_periods, min_days=2):
    """Kỳ liền trước có độ dài hợp lệ (bỏ các trạng thái chuyển tiếp chỉ tồn tại 1 ngày)."""
    for period in reversed(fund_periods[:-1]):
        if (period["last_date"] - period["first_date"]).days >= min_days:
            return period
    return fund_periods[-2] if len(fund_periods) >= 2 else None


def _ref_date(period):
    return period["report_date"] if period["report_date"] is not None else period["first_date"]


def _num(row, col):
    if row is None or col not in row:
        return np.nan
    value = row[col]
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _value(row):
    aum, pct = _num(row, "AUM_VND"), _num(row, "Ty_Le_Trong_Quy")
    return aum * pct / 100.0 if np.isfinite(aum) and np.isfinite(pct) else np.nan


def _price_per_share(row):
    shares = _num(row, "So_Co_Phieu")
    asset = _num(row, "Gia_Tri_Tai_San_VND")
    if not (np.isfinite(shares) and shares > 0):
        return np.nan
    if np.isfinite(asset) and asset > 0:
        return asset / shares
    value = _value(row)
    return value / shares if np.isfinite(value) else np.nan


def _cutoff_value(period):
    rows = period["rows"]
    if len(rows) < config.TOP_HOLDING_LIST_SIZE:
        return 0.0  # danh sách chưa đủ 10 mã → coi là đầy đủ danh mục cổ phiếu
    aum = float(rows["AUM_VND"].iloc[0])
    return aum * float(rows["Ty_Le_Trong_Quy"].min()) / 100.0


def compute_pair_flow(ticker, prev, cur, price_ratio_fn):
    """Dòng tiền của 1 quỹ với 1 mã giữa kỳ `prev` và `cur`."""
    row0 = prev["rows"].loc[ticker] if ticker in prev["rows"].index else None
    row1 = cur["rows"].loc[ticker] if ticker in cur["rows"].index else None
    ratio = price_ratio_fn(ticker, _ref_date(prev), _ref_date(cur))
    ratio_missing = not (isinstance(ratio, (int, float)) and np.isfinite(ratio) and ratio > 0)
    if ratio_missing:
        ratio = 1.0

    out = {
        "Ten_Quy": cur["fund"],
        "Ma_Co_Phieu": ticker,
        "Ky_Truoc": _ref_date(prev).strftime("%Y-%m-%d"),
        "Ky_Hien_Tai": _ref_date(cur).strftime("%Y-%m-%d"),
        "Ty_Le_Truoc_pct": _num(row0, "Ty_Le_Trong_Quy") if row0 is not None else 0.0,
        "Ty_Le_Hien_Tai_pct": _num(row1, "Ty_Le_Trong_Quy") if row1 is not None else 0.0,
        "CP_Truoc": _num(row0, "So_Co_Phieu"),
        "CP_Hien_Tai": _num(row1, "So_Co_Phieu"),
        "Phuong_Phap": "",
        "Dieu_Chinh_Chia_Tach": False,
        "Thieu_Gia": bool(ratio_missing),
    }

    shares0, shares1 = out["CP_Truoc"], out["CP_Hien_Tai"]
    p0, p1 = _price_per_share(row0), _price_per_share(row1)

    if row0 is not None and row1 is not None:
        if np.isfinite(shares0) and np.isfinite(shares1) and np.isfinite(p0) and np.isfinite(p1):
            adj = 1.0
            expected_p1 = p0 * ratio
            if p1 < config.SPLIT_PRICE_DROP * expected_p1:
                # Giá/CP trong báo cáo giảm mạnh hơn giá thị trường nhưng tổng giá trị gần như giữ nguyên
                # → chia tách / thưởng cổ phiếu, không phải quỹ mua thêm.
                value_change = abs((shares1 * p1) / (shares0 * p0 * ratio) - 1)
                if value_change < config.SPLIT_VALUE_TOLERANCE:
                    adj = expected_p1 / p1
                    out["Dieu_Chinh_Chia_Tach"] = True
            prev_value = shares0 * adj * p1
            cur_value = shares1 * p1
            out["Phuong_Phap"] = "SO_CO_PHIEU"
        else:
            prev_value = _value(row0) * ratio
            cur_value = _value(row1)
            out["Phuong_Phap"] = "GIA_TRI_DIEU_CHINH_GIA"
        flow = cur_value - prev_value
        noise = max(config.MIN_FLOW_ABS_VND, config.FLOW_NOISE_REL * abs(prev_value))
        status = "UNCHANGED" if abs(flow) < noise else ("INCREASE" if flow > 0 else "DECREASE")
    elif row1 is not None:
        cur_value = shares1 * p1 if np.isfinite(shares1) and np.isfinite(p1) else _value(row1)
        cutoff = _cutoff_value(prev) * ratio
        if cutoff > 0:
            prev_value = min(cutoff, cur_value)
            status = "ENTER_TOP10"
        else:
            prev_value = 0.0
            status = "NEW_BUY"
        flow = cur_value - prev_value
        out["Phuong_Phap"] = "CAN_TOP10" if cutoff > 0 else "MUA_MOI"
    else:
        if np.isfinite(shares0) and np.isfinite(p0):
            prev_value = shares0 * p0 * ratio
        else:
            prev_value = _value(row0) * ratio
        cutoff = _cutoff_value(cur)
        if cutoff > 0:
            cur_value = min(cutoff, prev_value)
            status = "LEFT_TOP10"
        else:
            cur_value = 0.0
            status = "EXIT"
        flow = cur_value - prev_value
        out["Phuong_Phap"] = "CAN_TOP10" if cutoff > 0 else "BAN_HET"

    out.update(
        {
            "Gia_Tri_Truoc_VND": prev_value,
            "Gia_Tri_Hien_Tai_VND": cur_value,
            "Dong_Tien_VND": flow,
            "Trang_Thai": status,
        }
    )
    return out


def compute_flows(history, run_date, price_ratio_fn, active_funds=None):
    """Trả về (pair_flow, ticker_flow, summary).

    active_funds: các quỹ có trong lần tải hiện tại (kể cả quỹ giữ lại do lỗi mạng). Quỹ khác
    (đóng, đổi tên, ngừng công bố) bị bỏ qua để danh mục cũ không bị tính là đang nắm giữ.
    """
    periods = build_fund_periods(history)
    run_date = pd.Timestamp(run_date).tz_localize(None).normalize()
    pairs, fund_info = [], []

    for fund, fund_periods in periods.items():
        if not fund_periods:
            continue
        if active_funds is not None and fund not in active_funds:
            fund_info.append({"Ten_Quy": fund, "Trang_Thai": "INACTIVE", "Ky_Hien_Tai": _ref_date(fund_periods[-1]).strftime("%Y-%m-%d")})
            continue
        cur = fund_periods[-1]
        cur_age = (run_date - cur["first_date"]).days
        if len(fund_periods) < 2:
            fund_info.append({"Ten_Quy": fund, "Trang_Thai": "NO_BASELINE", "Ky_Hien_Tai": _ref_date(cur).strftime("%Y-%m-%d")})
            for ticker, row in cur["rows"].iterrows():
                pairs.append(
                    {
                        "Ten_Quy": fund,
                        "Ma_Co_Phieu": ticker,
                        "Ky_Hien_Tai": _ref_date(cur).strftime("%Y-%m-%d"),
                        "Ty_Le_Hien_Tai_pct": _num(row, "Ty_Le_Trong_Quy"),
                        "Gia_Tri_Hien_Tai_VND": _value(row),
                        "Dong_Tien_VND": np.nan,
                        "Trang_Thai": "NO_BASELINE",
                    }
                )
            continue

        prev = _pick_previous_period(fund_periods)
        if prev["report_date_estimated"] and prev["report_date"] >= _ref_date(cur):
            # Ước lượng rơi sau kỳ hiện tại → lùi về kỳ báo cáo trước đó (≈ 1 tháng)
            prev["report_date"] = _ref_date(cur) - pd.Timedelta(days=30)
        stale = cur_age > STALE_PERIOD_DAYS
        fund_info.append(
            {
                "Ten_Quy": fund,
                "Trang_Thai": "STALE" if stale else "OK",
                "Ky_Truoc": _ref_date(prev).strftime("%Y-%m-%d"),
                "Ky_Hien_Tai": _ref_date(cur).strftime("%Y-%m-%d"),
                "Ky_Truoc_Uoc_Luong": bool(prev.get("report_date_estimated")),
                "Ngay_Cap_Nhat": cur["first_date"].strftime("%Y-%m-%d"),
            }
        )
        tickers = sorted(set(prev["rows"].index) | set(cur["rows"].index))
        for ticker in tickers:
            pair = compute_pair_flow(ticker, prev, cur, price_ratio_fn)
            if stale:
                pair["Trang_Thai"] = "STALE"
                pair["Dong_Tien_VND"] = np.nan
            pairs.append(pair)

    pair_flow = pd.DataFrame(pairs)
    ticker_flow = aggregate_ticker_flow(pair_flow)
    fund_df = pd.DataFrame(fund_info)

    active = fund_df[fund_df["Trang_Thai"] != "INACTIVE"] if not fund_df.empty else fund_df
    summary = {"funds_total": int(len(active))}
    if not fund_df.empty:
        ok = fund_df[fund_df["Trang_Thai"] == "OK"]
        summary.update(
            {
                "funds_with_baseline": int(len(ok)),
                "funds_no_baseline": int((fund_df["Trang_Thai"] == "NO_BASELINE").sum()),
                "funds_stale": int((fund_df["Trang_Thai"] == "STALE").sum()),
                "funds_inactive": int((fund_df["Trang_Thai"] == "INACTIVE").sum()),
                "period_prev": ok["Ky_Truoc"].mode().iloc[0] if not ok.empty else None,
                "period_current": ok["Ky_Hien_Tai"].mode().iloc[0] if not ok.empty else None,
                "funds": fund_df.to_dict(orient="records"),
            }
        )
    return pair_flow, ticker_flow, summary


def aggregate_ticker_flow(pair_flow):
    columns = [
        "Ma_Co_Phieu", "So_Luong_Quy", "Tong_Gia_Tri_Hien_Tai_VND", "Tong_Gia_Tri_Ky_Truoc_VND",
        "Dong_Tien_Rong_VND", "Dong_Tien_Mua_VND", "Dong_Tien_Ban_VND", "So_Quy_Tang", "So_Quy_Giam",
        "So_Quy_Mua_Moi", "So_Quy_Thoat", "Ty_Le_Dong_Tien", "Tin_Hieu_Dong_Tien", "Co_Du_Lieu_Dong_Tien",
    ]
    if pair_flow.empty:
        return pd.DataFrame(columns=columns)

    df = pair_flow.copy()
    held_now = df["Ty_Le_Hien_Tai_pct"].fillna(0) > 0  # có tên trong danh sách kỳ hiện tại
    has_flow = df["Dong_Tien_VND"].notna()
    flow = df["Dong_Tien_VND"].where(has_flow, 0.0)
    df["_held"] = held_now.astype(int)
    df["_cur"] = df["Gia_Tri_Hien_Tai_VND"].where(held_now, 0.0)
    df["_prev"] = df.get("Gia_Tri_Truoc_VND", pd.Series(np.nan, index=df.index)).where(has_flow, 0.0).fillna(0.0)
    df["_flow"] = flow
    df["_buy"] = flow.clip(lower=0)
    df["_sell"] = flow.clip(upper=0)
    df["_inc"] = df["Trang_Thai"].isin(BUY_STATUSES).astype(int)
    df["_dec"] = df["Trang_Thai"].isin(SELL_STATUSES).astype(int)
    df["_new"] = df["Trang_Thai"].isin({"NEW_BUY", "ENTER_TOP10"}).astype(int)
    df["_exit"] = df["Trang_Thai"].isin({"EXIT", "LEFT_TOP10"}).astype(int)
    df["_has"] = has_flow.astype(int)

    out = df.groupby("Ma_Co_Phieu").agg(
        So_Luong_Quy=("_held", "sum"),
        Tong_Gia_Tri_Hien_Tai_VND=("_cur", "sum"),
        Tong_Gia_Tri_Ky_Truoc_VND=("_prev", "sum"),
        Dong_Tien_Rong_VND=("_flow", "sum"),
        Dong_Tien_Mua_VND=("_buy", "sum"),
        Dong_Tien_Ban_VND=("_sell", "sum"),
        So_Quy_Tang=("_inc", "sum"),
        So_Quy_Giam=("_dec", "sum"),
        So_Quy_Mua_Moi=("_new", "sum"),
        So_Quy_Thoat=("_exit", "sum"),
        Co_Du_Lieu_Dong_Tien=("_has", "max"),
    ).reset_index()
    out["Co_Du_Lieu_Dong_Tien"] = out["Co_Du_Lieu_Dong_Tien"].astype(bool)
    out.loc[~out["Co_Du_Lieu_Dong_Tien"], "Dong_Tien_Rong_VND"] = np.nan
    out["Ty_Le_Dong_Tien"] = np.where(
        out["Tong_Gia_Tri_Ky_Truoc_VND"] > 0, out["Dong_Tien_Rong_VND"] / out["Tong_Gia_Tri_Ky_Truoc_VND"], np.nan
    )
    net = out["Dong_Tien_Rong_VND"]
    out["Tin_Hieu_Dong_Tien"] = np.select(
        [
            (net >= config.MIN_FLOW_ABS_VND) & (out["So_Quy_Tang"] >= out["So_Quy_Giam"]),
            (net <= -config.MIN_FLOW_ABS_VND) & (out["So_Quy_Giam"] >= out["So_Quy_Tang"]),
        ],
        ["MUA", "BAN"],
        default="TRUNG_TINH",
    )
    return out[columns]
