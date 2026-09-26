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


# ---------------------------------------------------------------- nhiều nguồn giá
def test_parse_ssi_giu_nguyen_don_vi_nghin_vnd():
    payload = {"data": {"t": [1788912000], "o": [21.9], "h": [22.2], "l": [21.85], "c": [22.05], "v": [22432800]}}
    df = price_store.parse_ssi(payload)
    assert df["close"].iloc[0] == pytest.approx(22.05)
    assert df["time"].iloc[0] == pd.Timestamp("2026-09-09")


def test_parse_vietcap_chia_1000_va_doc_timestamp_dang_chuoi():
    payload = [{"symbol": "HPG", "t": ["1788912000"], "o": [21900], "h": [22200], "l": [21850], "c": [22050], "v": [22432800]}]
    df = price_store.parse_vietcap(payload)
    assert df["close"].iloc[0] == pytest.approx(22.05)      # cùng đơn vị với SSI
    assert df["volume"].iloc[0] == 22432800                 # khối lượng giữ nguyên
    assert df["time"].iloc[0] == pd.Timestamp("2026-09-09")


def test_parse_khi_khong_co_du_lieu():
    assert price_store.parse_ssi({"data": {}}).empty
    assert price_store.parse_vietcap([]).empty


def test_tu_chuyen_sang_nguon_con_lai_khi_mot_nguon_bi_chan(monkeypatch):
    price_store.reset_sources()
    goi = {"ssi": 0, "vietcap": 0}

    def ssi_bi_chan(ticker, start, end, retries=2):
        goi["ssi"] += 1
        return None

    def vietcap_ok(ticker, start, end, retries=2):
        goi["vietcap"] += 1
        return bars("2026-01-01", "2026-09-25")

    monkeypatch.setitem(price_store.FETCHERS, "ssi", ssi_bi_chan)
    monkeypatch.setitem(price_store.FETCHERS, "vietcap", vietcap_ok)

    for ticker in ("AAA", "BBB", "CCC", "DDD", "EEE"):
        df = price_store.fetch_auto(ticker, "2026-01-01", "2026-09-25")
        assert df is not None and not df.empty

    # Nguồn chạy được phải được ưu tiên, nguồn bị chặn chỉ thử vài lần rồi bỏ qua
    assert goi["vietcap"] == 5
    assert goi["ssi"] <= price_store.MAX_SOURCE_FAILURES
    assert price_store.source_report()["vietcap"]["ok"] == 5


def test_ca_hai_nguon_hong_thi_tra_none(monkeypatch):
    price_store.reset_sources()
    monkeypatch.setitem(price_store.FETCHERS, "ssi", lambda *a, **k: None)
    monkeypatch.setitem(price_store.FETCHERS, "vietcap", lambda *a, **k: None)
    assert price_store.fetch_auto("AAA", "2026-01-01", "2026-09-25") is None
