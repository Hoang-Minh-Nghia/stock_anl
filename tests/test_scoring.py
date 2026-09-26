import numpy as np
import pandas as pd

from smart_money import config, scoring


def make_universe(n=12):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        rows.append(
            {
                "Ma_Co_Phieu": f"S{i:02d}",
                "Nganh": "Ngân hàng" if i < 6 else "Bán lẻ",
                "Nhom_Nganh": "Tài chính" if i < 6 else "Hàng hóa không thiết yếu",
                "Loai_CK": "stock",
                "PE": 5 + i,
                "PB": 1 + i * 0.2,
                "ROE_pct": 10 + i,
                "ROA_pct": 1 + i * 0.3,
                "Tang_Truong_LNST_pct": rng.normal(10, 20),
                "Tang_Truong_DT_pct": rng.normal(10, 10),
                "Mom_6_1": rng.normal(0.05, 0.1),
                "Ret_3M": rng.normal(0.02, 0.05),
                "Volatility_60D": 0.2 + i * 0.01,
                "Max_Drawdown_6M": -0.1 - i * 0.01,
                "ADV_20D_VND": 10e9,
                "Von_Hoa_VND": 10_000e9,
                "Tong_Gia_Tri_Hien_Tai_VND": 100e9 + i * 10e9,
                "Dong_Tien_Rong_VND": (i - 6) * 1e9,
                "Upside_pct": 20.0,
                "So_Bao_Cao_MT": 2,
            }
        )
    return pd.DataFrame(rows)


def test_weights_sum_to_one_and_scores_in_range():
    assert abs(sum(config.FACTOR_WEIGHTS.values()) - 1) < 1e-9
    scored = scoring.score_universe(make_universe())
    assert scored["Final_Score"].between(0, 100).all()
    assert scored["Xep_Hang"].min() == 1


def test_missing_analyst_target_is_neutral_not_penalized():
    df = make_universe()
    df.loc[0, ["Upside_pct", "So_Bao_Cao_MT"]] = [np.nan, 0]
    scored = scoring.score_universe(df).set_index("Ma_Co_Phieu")
    assert scored.loc["S00", "Score_Upside"] == 50.0
    assert scored.loc["S00", "Data_Coverage"] < 1.0


def test_missing_liquidity_is_excluded_not_passed():
    df = make_universe()
    df.loc[1, "ADV_20D_VND"] = np.nan
    df.loc[2, "ADV_20D_VND"] = 1e8
    scored = scoring.score_universe(df).set_index("Ma_Co_Phieu")
    assert scored.loc["S01", "Loai_Tru"] == "Thiếu dữ liệu thanh khoản"
    assert scored.loc["S02", "Loai_Tru"] == "Thanh khoản thấp"
    assert np.isnan(scored.loc["S01", "Final_Score"])


def test_etf_is_excluded():
    df = make_universe()
    df.loc[3, "Ma_Co_Phieu"] = "FUEVFVND"
    scored = scoring.score_universe(df).set_index("Ma_Co_Phieu")
    assert scored.loc["FUEVFVND", "Loai_Tru"].startswith("ETF")


def test_loss_making_company_ranks_last_on_value():
    df = make_universe()
    df.loc[0, "PE"] = -8
    scored = scoring.score_universe(df).set_index("Ma_Co_Phieu")
    banks = scored[scored["Nganh"] == "Ngân hàng"]
    assert banks["Rank_EY"].idxmin() == "S00"


def test_value_rank_is_sector_neutral():
    df = make_universe()
    scored = scoring.score_universe(df)
    # Mỗi ngành có mã rẻ nhất đạt hạng cao nhất trong ngành
    for _, group in scored.groupby("Nganh"):
        assert group["Rank_EY"].max() == 100.0
