import pandas as pd
import pytest

from market_data import price_store


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(price_store, "PRICE_DIR", tmp_path)
    return tmp_path


def bars(start, end, price=10.0, factor=1.0):
    days = pd.bdate_range(start, end)
    return pd.DataFrame({"time": days, "open": price * factor, "high": price * factor, "low": price * factor, "close": price * factor, "volume": 1000})


class FakeSSI:
    def __init__(self, full):
        self.full = full
        self.calls = []

    def __call__(self, ticker, start, end):
        self.calls.append((start, end))
        mask = (self.full["time"] >= pd.Timestamp(start)) & (self.full["time"] <= pd.Timestamp(end))
        return self.full[mask].reset_index(drop=True)


def test_first_run_downloads_full_history_and_skips_unclosed_session():
    fake = FakeSSI(bars("2026-01-01", "2026-09-15"))
    df, status = price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-14"), fetch=fake)
    assert status == "full"
    assert df["time"].max() == pd.Timestamp("2026-09-14")  # nến 15/09 chưa đóng cửa không được lưu


def test_up_to_date_store_makes_no_request():
    fake = FakeSSI(bars("2026-01-01", "2026-09-15"))
    price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-15"), fetch=fake)
    fake.calls.clear()
    _, status = price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-15"), fetch=fake)
    assert status == "cached" and fake.calls == []


def test_missing_days_are_appended_with_small_request():
    fake = FakeSSI(bars("2026-01-01", "2026-09-15"))
    price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-01"), fetch=fake)
    fake.calls.clear()
    df, status = price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-15"), fetch=fake)
    assert status == "appended"
    assert df["time"].max() == pd.Timestamp("2026-09-15")
    assert df["time"].is_unique
    assert fake.calls[0][0] >= "2026-08-20"  # chỉ tải đoạn gần, không tải lại từ đầu


def test_readjusted_history_triggers_full_reload():
    old = FakeSSI(bars("2026-01-01", "2026-09-15"))
    price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-01"), fetch=old)
    adjusted = FakeSSI(bars("2026-01-01", "2026-09-15", factor=0.9))  # chia cổ tức → toàn bộ quá khứ giảm 10%
    df, status = price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-15"), fetch=adjusted)
    assert status == "readjusted"
    assert df["close"].nunique() == 1 and df["close"].iloc[0] == pytest.approx(9.0)


def test_network_failure_keeps_existing_data():
    fake = FakeSSI(bars("2026-01-01", "2026-09-15"))
    price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-01"), fetch=fake)
    df, status = price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-15"), fetch=lambda *a: None)
    assert status == "failed" and df["time"].max() == pd.Timestamp("2026-09-01")


def test_last_complete_session_handles_intraday_and_weekend():
    tz = price_store.VN_TZ
    assert price_store.last_complete_session(pd.Timestamp("2026-09-15 10:00", tz=tz)) == pd.Timestamp("2026-09-14")
    assert price_store.last_complete_session(pd.Timestamp("2026-09-15 15:30", tz=tz)) == pd.Timestamp("2026-09-15")
    assert price_store.last_complete_session(pd.Timestamp("2026-09-13 12:00", tz=tz)) == pd.Timestamp("2026-09-11")  # Chủ nhật → thứ Sáu
    assert price_store.last_complete_session(pd.Timestamp("2026-09-14 09:00", tz=tz)) == pd.Timestamp("2026-09-11")  # sáng thứ Hai
