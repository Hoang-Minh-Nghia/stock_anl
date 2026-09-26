import numpy as np
import pandas as pd
import pytest

from smart_money import config, flow
from smart_money.snapshots import carry_forward_failed_funds

AUM = 1_000_000_000_000  # 1.000 tỷ


def snap(stamp, fund, holdings, aum=AUM, report=None, with_volume=False):
    """holdings: {ticker: (pct, price_vnd_per_share)}"""
    rows = []
    for ticker, (pct, price) in holdings.items():
        value = aum * pct / 100
        rows.append(
            {
                "Snapshot_Stamp": stamp,
                "Snapshot_Date": stamp[:10],
                "Ten_Quy": fund,
                "Ma_Co_Phieu": ticker,
                "Nganh": "X",
                "AUM_VND": aum,
                "Ty_Le_Trong_Quy": pct,
                "Gia_Tri_VND": value,
                "So_Co_Phieu": value / price if with_volume else np.nan,
                "Gia_Tri_Tai_San_VND": value if with_volume else np.nan,
                "Report_Date": report,
            }
        )
    return rows


def history(*snapshots):
    return pd.DataFrame([row for s in snapshots for row in s])


def no_price_change(*_):
    return 1.0


def test_same_holdings_across_days_is_one_period():
    h = history(
        snap("2026-08-01_030000", "F", {"AAA": (5, 10_000)}),
        snap("2026-08-02_030000", "F", {"AAA": (5, 10_000)}),
        snap("2026-08-03_030000", "F", {"AAA": (5, 10_000)}),
    )
    periods = flow.build_fund_periods(h)
    assert len(periods["F"]) == 1


def test_first_period_has_no_baseline_and_no_fake_buy():
    h = history(snap("2026-08-01_030000", "F", {"AAA": (5, 10_000)}))
    pair, ticker, summary = flow.compute_flows(h, "2026-08-02", no_price_change)
    assert pair["Trang_Thai"].tolist() == ["NO_BASELINE"]
    assert np.isnan(ticker.loc[0, "Dong_Tien_Rong_VND"])
    assert summary["funds_no_baseline"] == 1


def test_price_rise_without_trading_is_not_a_buy():
    # Tỷ trọng tăng 5% → 5.5% chỉ vì giá tăng 10%, AUM không đổi về số CP → không phải mua
    h = history(
        snap("2026-07-01_030000", "F", {"AAA": (5.0, 10_000)}),
        snap("2026-07-02_030000", "F", {"AAA": (5.0, 10_000)}),
        snap("2026-08-01_030000", "F", {"AAA": (5.5, 11_000)}),
    )
    pair, _, _ = flow.compute_flows(h, "2026-08-02", lambda *_: 1.10)
    row = pair.iloc[0]
    assert row["Trang_Thai"] == "UNCHANGED"
    assert abs(row["Dong_Tien_VND"]) < config.MIN_FLOW_ABS_VND


def test_share_based_flow_uses_share_change():
    prev = snap("2026-07-01_030000", "F", {"AAA": (5.0, 10_000)}, report="2026-06-30", with_volume=True)
    prev2 = snap("2026-07-05_030000", "F", {"AAA": (5.0, 10_000)}, report="2026-06-30", with_volume=True)
    cur = snap("2026-08-01_030000", "F", {"AAA": (6.0, 10_000)}, report="2026-07-31", with_volume=True)
    pair, _, _ = flow.compute_flows(history(prev, prev2, cur), "2026-08-02", no_price_change)
    row = pair.iloc[0]
    assert row["Phuong_Phap"] == "SO_CO_PHIEU"
    assert row["Trang_Thai"] == "INCREASE"
    assert row["Dong_Tien_VND"] == pytest.approx(AUM * 0.01)  # thêm 1% AUM


def test_bonus_share_issue_is_not_a_buy():
    # Thưởng CP 2:1 → số CP ×2, giá/CP ÷2, giá trị giữ nguyên. Giá SSI (đã điều chỉnh) không đổi.
    prev = snap("2026-07-01_030000", "F", {"AAA": (5.0, 20_000)}, report="2026-06-30", with_volume=True)
    prev2 = snap("2026-07-05_030000", "F", {"AAA": (5.0, 20_000)}, report="2026-06-30", with_volume=True)
    cur = snap("2026-08-01_030000", "F", {"AAA": (5.01, 10_000)}, report="2026-07-31", with_volume=True)
    pair, _, _ = flow.compute_flows(history(prev, prev2, cur), "2026-08-02", no_price_change)
    row = pair.iloc[0]
    assert bool(row["Dieu_Chinh_Chia_Tach"])
    assert row["Trang_Thai"] == "UNCHANGED"


def test_dropping_out_of_full_top10_is_bounded_not_full_exit():
    top10 = {f"T{i:02d}": (10 - i * 0.5, 10_000) for i in range(10)}  # min pct = 5.5
    prev_holdings = dict(top10)
    cur_holdings = {k: v for k, v in top10.items() if k != "T00"}
    cur_holdings["NEW"] = (5.6, 10_000)
    h = history(
        snap("2026-07-01_030000", "F", prev_holdings),
        snap("2026-07-05_030000", "F", prev_holdings),
        snap("2026-08-01_030000", "F", cur_holdings),
    )
    pair, _, _ = flow.compute_flows(h, "2026-08-02", no_price_change)
    left = pair[pair["Ma_Co_Phieu"] == "T00"].iloc[0]
    assert left["Trang_Thai"] == "LEFT_TOP10"
    # Trước 10% AUM, sau tối đa bằng mã nhỏ nhất hiện tại (5.5%) → bán ít nhất 4.5% AUM, không phải 10%
    assert left["Dong_Tien_VND"] == pytest.approx(-AUM * 0.045)
    entered = pair[pair["Ma_Co_Phieu"] == "NEW"].iloc[0]
    assert entered["Trang_Thai"] == "ENTER_TOP10"


def test_exit_when_list_not_full_is_full_exit():
    h = history(
        snap("2026-07-01_030000", "F", {"AAA": (5, 10_000), "BBB": (4, 10_000)}),
        snap("2026-07-05_030000", "F", {"AAA": (5, 10_000), "BBB": (4, 10_000)}),
        snap("2026-08-01_030000", "F", {"AAA": (5, 10_000)}),
    )
    pair, ticker, _ = flow.compute_flows(h, "2026-08-02", no_price_change)
    exit_row = pair[pair["Ma_Co_Phieu"] == "BBB"].iloc[0]
    assert exit_row["Trang_Thai"] == "EXIT"
    assert exit_row["Dong_Tien_VND"] == pytest.approx(-AUM * 0.04)
    bbb = ticker[ticker["Ma_Co_Phieu"] == "BBB"].iloc[0]
    assert bbb["So_Luong_Quy"] == 0 and bbb["So_Quy_Thoat"] == 1


def test_one_day_transition_period_is_skipped():
    h = history(
        snap("2026-07-01_030000", "F", {"AAA": (5, 10_000)}),
        snap("2026-07-20_030000", "F", {"AAA": (5, 10_000)}),
        snap("2026-08-01_030000", "F", {"AAA": (5.3, 10_000)}),  # cập nhật dở dang 1 ngày
        snap("2026-08-02_030000", "F", {"AAA": (6, 10_000)}),
    )
    _, _, summary = flow.compute_flows(h, "2026-08-03", no_price_change)
    assert summary["funds"][0]["Ky_Truoc"] < "2026-07-20"


def test_inactive_fund_holdings_are_ignored():
    h = history(
        snap("2026-07-01_030000", "OLD", {"AAA": (5, 10_000)}),
        snap("2026-07-01_030000", "F", {"BBB": (5, 10_000)}),
        snap("2026-08-01_030000", "F", {"BBB": (5, 10_000)}),
    )
    pair, ticker, summary = flow.compute_flows(h, "2026-08-02", no_price_change, active_funds={"F"})
    assert "AAA" not in set(ticker["Ma_Co_Phieu"])
    assert summary["funds_inactive"] == 1 and summary["funds_total"] == 1


def test_failed_fund_is_carried_forward():
    hist = history(snap("2026-08-01_030000", "F", {"AAA": (5, 10_000)}), snap("2026-08-01_030000", "G", {"BBB": (5, 10_000)}))
    current = history(snap("2026-08-02_030000", "G", {"BBB": (5, 10_000)}))
    merged, carried = carry_forward_failed_funds(current, hist, [{"id": 1, "name": "F", "error": "timeout"}])
    assert carried == ["F"]
    assert set(merged["Ten_Quy"]) == {"F", "G"}
    assert (merged[merged["Ten_Quy"] == "F"]["Snapshot_Stamp"] == "2026-08-02_030000").all()
