"""Mô hình chấm điểm đa nhân tố + phân nhóm chiến lược.

Mỗi nhân tố được winsorize, xếp hạng phần trăm (0-100). Nhân tố định giá / chất lượng xếp hạng
TRONG NGÀNH (sector-neutral) để không thiên vị ngành có P/E thấp hoặc ROE cao cấu trúc (ngân hàng).
Thiếu dữ liệu → điểm trung lập 50, ghi nhận qua `Data_Coverage`.
"""

import re

import numpy as np
import pandas as pd

from . import config

_WS = re.compile(r"\s+")


def normalize_text(value):
    return _WS.sub(" ", str(value or "").strip().lower())


def _winsorize(series):
    s = pd.to_numeric(series, errors="coerce")
    valid = s.dropna()
    if len(valid) < 5:
        return s
    lo, hi = valid.quantile(config.WINSOR_QUANTILES[0]), valid.quantile(config.WINSOR_QUANTILES[1])
    return s.clip(lower=lo, upper=hi)


def pct_rank(series, higher_is_better=True):
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() < 2:
        return pd.Series(np.where(s.notna(), 50.0, np.nan), index=s.index)
    return s.rank(pct=True, ascending=higher_is_better) * 100


def sector_rank(df, column, group_col="Nhom_Nganh_Gop", higher_is_better=True):
    values = _winsorize(df[column])
    overall = pct_rank(values, higher_is_better)
    result = overall.copy()
    for _, idx in df.groupby(group_col).groups.items():
        sub = values.loc[idx]
        if sub.notna().sum() >= config.MIN_SECTOR_SIZE:
            result.loc[idx] = pct_rank(sub, higher_is_better)
    return result


def _mean_available(*series):
    frame = pd.concat(series, axis=1)
    return frame.mean(axis=1, skipna=True)


def apply_filters(df):
    """Gắn cột `Loai_Tru` (lý do loại) — không xoá dòng để giao diện còn hiển thị."""
    df = df.copy()
    reasons = pd.Series("", index=df.index)
    is_etf = df["Ma_Co_Phieu"].str.startswith(config.ETF_PREFIXES)
    if "Loai_CK" in df:
        is_etf |= df["Loai_CK"].fillna("stock").str.lower().ne("stock")
    reasons = reasons.mask(is_etf, "ETF / không phải cổ phiếu")
    adv = pd.to_numeric(df.get("ADV_20D_VND"), errors="coerce")
    reasons = reasons.mask((reasons == "") & adv.isna(), "Thiếu dữ liệu thanh khoản")
    reasons = reasons.mask((reasons == "") & (adv < config.MIN_ADV_VND), "Thanh khoản thấp")
    df["Loai_Tru"] = reasons.where(reasons != "", None)
    return df


def score_universe(df):
    df = apply_filters(df)
    eligible = df[df["Loai_Tru"].isna()].copy()
    if eligible.empty:
        df["Final_Score"] = np.nan
        return df

    sector = eligible["Nhom_Nganh"].fillna(eligible["Nganh"]).fillna("Khác")
    counts = sector.value_counts()
    eligible["Nhom_Nganh_Gop"] = sector.where(sector.map(counts) >= config.MIN_SECTOR_SIZE, "Khác")

    pe = pd.to_numeric(eligible["PE"], errors="coerce")
    pb = pd.to_numeric(eligible["PB"], errors="coerce")
    # Earnings yield: P/E âm (lỗ) → giá trị âm → tự động bị xếp cuối
    eligible["Earnings_Yield"] = np.where(pe.notna() & (pe != 0), 1 / pe, np.nan)
    eligible["Book_Yield"] = np.where(pb > 0, 1 / pb, np.nan)

    eligible["Rank_EY"] = sector_rank(eligible, "Earnings_Yield")
    eligible["Rank_BY"] = sector_rank(eligible, "Book_Yield")
    eligible["Rank_ROE"] = sector_rank(eligible, "ROE_pct")
    eligible["Rank_ROA"] = sector_rank(eligible, "ROA_pct")
    eligible["Rank_NI_Growth"] = pct_rank(_winsorize(eligible["Tang_Truong_LNST_pct"]))
    eligible["Rank_Rev_Growth"] = pct_rank(_winsorize(eligible["Tang_Truong_DT_pct"]))
    eligible["Rank_Mom_6_1"] = pct_rank(_winsorize(eligible["Mom_6_1"]))
    eligible["Rank_Low_Vol"] = pct_rank(eligible["Volatility_60D"], higher_is_better=False)
    eligible["Rank_Low_DD"] = pct_rank(eligible["Max_Drawdown_6M"])  # ít âm hơn = tốt hơn

    mcap = pd.to_numeric(eligible["Von_Hoa_VND"], errors="coerce")
    eligible["Ty_Le_So_Huu_Quy_pct"] = np.where(mcap > 0, eligible["Tong_Gia_Tri_Hien_Tai_VND"] / mcap * 100, np.nan)
    eligible["Dong_Tien_Tren_Von_Hoa_pct"] = np.where(mcap > 0, eligible["Dong_Tien_Rong_VND"] / mcap * 100, np.nan)
    eligible["Rank_Ownership"] = pct_rank(_winsorize(eligible["Ty_Le_So_Huu_Quy_pct"]))
    eligible["Rank_Net_Flow"] = pct_rank(_winsorize(eligible["Dong_Tien_Tren_Von_Hoa_pct"]))

    upside = pd.to_numeric(eligible["Upside_pct"], errors="coerce").clip(-50, 100)
    eligible["Rank_Upside"] = pct_rank(upside.where(eligible["So_Bao_Cao_MT"].fillna(0) > 0))

    raw_factors = {
        "Score_Value": _mean_available(eligible["Rank_EY"], eligible["Rank_BY"]),
        "Score_Quality": _mean_available(eligible["Rank_ROE"], eligible["Rank_ROA"]),
        "Score_Growth": _mean_available(eligible["Rank_NI_Growth"], eligible["Rank_Rev_Growth"]),
        "Score_Momentum": eligible["Rank_Mom_6_1"],
        # Biến động thấp mạnh giai đoạn gần đây, sụt giảm thấp mạnh trong dài hạn → 50/50
        "Score_LowRisk": _mean_available(eligible["Rank_Low_Vol"], eligible["Rank_Low_DD"]),
        "Score_SmartMoney": _mean_available(eligible["Rank_Ownership"], eligible["Rank_Net_Flow"]),
        "Score_Upside": eligible["Rank_Upside"],
    }
    available = pd.DataFrame({k: v.notna() for k, v in raw_factors.items()})
    eligible["Data_Coverage"] = (available * pd.Series(config.FACTOR_WEIGHTS)).sum(axis=1) / sum(config.FACTOR_WEIGHTS.values())

    final = pd.Series(0.0, index=eligible.index)
    for name, weight in config.FACTOR_WEIGHTS.items():
        eligible[name] = raw_factors[name].fillna(50.0)
        final += eligible[name] * weight
    eligible["Final_Score"] = final / sum(config.FACTOR_WEIGHTS.values())
    eligible["Canh_Bao_Du_Lieu"] = np.where(eligible["Data_Coverage"] < config.MIN_DATA_COVERAGE, "Thiếu nhiều dữ liệu", None)
    eligible["Xep_Hang"] = eligible["Final_Score"].rank(ascending=False, method="min").astype(int)

    new_cols = [c for c in eligible.columns if c not in df.columns]
    df = df.join(eligible[new_cols])
    df["Xep_Hang"] = df["Xep_Hang"].astype("Int64")
    return df.sort_values(["Final_Score", "Tong_Gia_Tri_Hien_Tai_VND"], ascending=[False, False], na_position="last")


def _sector_text(row):
    return normalize_text(" | ".join(str(row.get(c) or "") for c in ("Nganh", "Nhom_Nganh", "Nganh_Chi_Tiet")))


def classify_row(row):
    text = _sector_text(row)
    text_no_nonessential = text.replace("không thiết yếu", "")
    is_defensive = any(k in text_no_nonessential for k in config.DEFENSIVE_KEYWORDS)
    is_cyclical = any(k in text for k in config.CYCLICAL_KEYWORDS) and not is_defensive

    roe = pd.to_numeric(row.get("ROE_pct"), errors="coerce")
    pe = pd.to_numeric(row.get("PE"), errors="coerce")
    growth = pd.to_numeric(row.get("Tang_Truong_LNST_pct"), errors="coerce")
    dividend = pd.to_numeric(row.get("Co_Tuc_pct"), errors="coerce")
    roe = 0.0 if pd.isna(roe) else float(roe)
    growth = np.nan if pd.isna(growth) else float(growth)

    if is_cyclical:
        return config.GROUP_CYCLICAL
    if roe >= 20 or (roe >= 15 and np.isfinite(growth) and growth >= 15):
        return config.GROUP_GROWTH
    if is_defensive:
        return config.GROUP_DEFENSIVE
    if (pd.notna(pe) and 0 < pe < 12 and roe > 10) or (pd.notna(dividend) and dividend >= 4 and roe > 8):
        return config.GROUP_DEFENSIVE
    return config.GROUP_NEUTRAL


def classify_strategy_groups(df):
    df = df.copy()
    df["Nhom_Chien_Luoc"] = df.apply(classify_row, axis=1) if not df.empty else []
    return df
