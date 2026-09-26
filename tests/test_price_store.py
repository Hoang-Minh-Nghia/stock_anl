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


def test_parse_vietcap_batch_tach_theo_ma():
    payload = [
        {"symbol": "HPG", "t": ["1788912000"], "o": [21900], "h": [22200], "l": [21850], "c": [22050], "v": [100]},
        {"symbol": "VCB", "t": ["1788912000"], "o": [60000], "h": [61000], "l": [59500], "c": [60500], "v": [200]},
    ]
    d = price_store.parse_vietcap_batch(payload)
    assert set(d) == {"HPG", "VCB"}
    assert d["HPG"]["close"].iloc[0] == pytest.approx(22.05)
    assert d["VCB"]["close"].iloc[0] == pytest.approx(60.5)


def test_update_many_lay_theo_lo_thay_vi_goi_tung_ma(monkeypatch):
    """90 mã phải đi trong vài lượt gọi, không phải mỗi mã một lượt (nguồn chặn theo số lượt)."""
    price_store.reset_sources()
    tickers = [f"T{i:03d}" for i in range(65)]
    lo_da_goi = []

    def batch(ms, start, end, retries=2):
        lo_da_goi.append(list(ms))
        return {m.upper(): bars("2026-01-01", "2026-09-25") for m in ms}

    monkeypatch.setattr(price_store, "fetch_vietcap_batch", batch)
    monkeypatch.setattr(price_store, "fetch_auto", lambda *a, **k: pytest.fail("không được gọi lẻ từng mã"))

    frames, stats = price_store.update_many(tickers, workers=2, session_date=pd.Timestamp("2026-09-25"))
    assert stats.get("full") and len(stats["full"]) == 65
    assert all(frames[t] is not None for t in tickers)
    assert len(lo_da_goi) == 3                      # 65 mã / 30 mã mỗi lượt
    assert sum(len(x) for x in lo_da_goi) == 65


def test_kho_da_du_thi_khong_goi_mang(monkeypatch):
    price_store.reset_sources()
    fake = FakeSSI(bars("2026-01-01", "2026-09-25"))
    price_store.update_ticker("AAA", session_date=pd.Timestamp("2026-09-25"), fetch=fake)
    monkeypatch.setattr(price_store, "fetch_vietcap_batch", lambda *a, **k: pytest.fail("không được gọi mạng"))
    monkeypatch.setattr(price_store, "fetch_auto", lambda *a, **k: pytest.fail("không được gọi mạng"))
    _, stats = price_store.update_many(["AAA"], session_date=pd.Timestamp("2026-09-25"))
    assert stats == {"cached": ["AAA"]}
