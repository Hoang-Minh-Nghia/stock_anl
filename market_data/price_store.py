"""Kho giá ngày cục bộ dùng chung cho Smart Money và AI: `data/prices/{MÃ}.csv`.

Mỗi lần cập nhật chỉ tải những ngày còn thiếu từ SSI:
- Đã có đủ tới phiên gần nhất → không gọi mạng.
- Thiếu → tải từ (ngày cuối − `overlap` ngày) và so khớp đoạn chồng lấn. Nếu giá cũ bị lệch
  (SSI đã điều chỉnh lại quá khứ do cổ tức / thưởng cổ phiếu) → tải lại toàn bộ lịch sử mã đó,
  tránh bước nhảy giá giả tại điểm nối.
- Nến của phiên đang giao dịch (trước 15:05) không được lưu.

Hai nguồn giá, tự chuyển khi một nguồn bị chặn:
- SSI iBoard: chạy được từ Việt Nam, bị chặn 403 với IP nước ngoài.
- Vietcap (VCI): chạy được từ máy chủ nước ngoài (GitHub Actions).
Nguồn nào lỗi liên tiếp sẽ bị bỏ qua cho các mã còn lại trong cùng lần chạy.

Giá đơn vị nghìn VND, đã điều chỉnh.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
PRICE_DIR = ROOT_DIR / "data" / "prices"
VN_TZ = "Asia/Ho_Chi_Minh"
HISTORY_START = "2000-01-01"
SSI_HISTORY_URL = "https://iboard-api.ssi.com.vn/statistics/charts/history"
VIETCAP_CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap"
MAX_SOURCE_FAILURES = 3
MAX_UPDATE_SECONDS = 600  # tổng thời gian tối đa cho bước cập nhật giá
BATCH_SIZE = 30           # số mã lấy trong một request tới Vietcap   # một nguồn lỗi liên tiếp bấy nhiêu lần (chưa lần nào thành công) thì bỏ qua
COLUMNS = ["time", "open", "high", "low", "close", "volume"]
MARKET_CLOSE = (15, 5)
OVERLAP_DAYS = 10
ADJUST_TOLERANCE = 0.005  # lệch > 0.5% ở đoạn chồng lấn → giá đã được điều chỉnh lại

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0"})
_file_locks = {}
_locks_guard = threading.Lock()


def _lock_for(ticker):
    with _locks_guard:
        return _file_locks.setdefault(ticker, threading.Lock())


def now_vn():
    return pd.Timestamp.now(tz=VN_TZ)


def last_complete_session(now=None):
    """Ngày phiên giao dịch gần nhất đã đóng cửa (bỏ qua cuối tuần; ngày lễ tự xử lý vì SSI không trả nến)."""
    now = now or now_vn()
    day = now.normalize().tz_localize(None)
    if (now.hour, now.minute) < MARKET_CLOSE:
        day -= pd.Timedelta(days=1)
    while day.weekday() >= 5:
        day -= pd.Timedelta(days=1)
    return day


def _frame_from_arrays(times, opens, highs, lows, closes, volumes, price_divisor=1.0):
    df = pd.DataFrame(
        {
            "time": pd.to_datetime([int(t) for t in times], unit="s", utc=True)
            .tz_convert(VN_TZ)
            .tz_localize(None)
            .normalize(),
            "open": pd.to_numeric(opens, errors="coerce") / price_divisor,
            "high": pd.to_numeric(highs, errors="coerce") / price_divisor,
            "low": pd.to_numeric(lows, errors="coerce") / price_divisor,
            "close": pd.to_numeric(closes, errors="coerce") / price_divisor,
            "volume": pd.to_numeric(volumes, errors="coerce"),
        }
    )
    return df.dropna(subset=["close"]).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def parse_ssi(payload):
    """SSI trả giá theo NGHÌN VND."""
    data = (payload or {}).get("data") or {}
    if not data.get("t"):
        return pd.DataFrame(columns=COLUMNS)
    return _frame_from_arrays(data["t"], data.get("o"), data.get("h"), data.get("l"), data.get("c"), data.get("v"))


def parse_vietcap(payload):
    """Vietcap trả giá theo VND → chia 1000 cho cùng đơn vị với SSI."""
    rows = payload if isinstance(payload, list) else []
    if not rows or not rows[0].get("t"):
        return pd.DataFrame(columns=COLUMNS)
    d = rows[0]
    return _frame_from_arrays(d["t"], d.get("o"), d.get("h"), d.get("l"), d.get("c"), d.get("v"), price_divisor=1000.0)


def _range(start, end):
    return (
        int(pd.Timestamp(start).tz_localize(VN_TZ).timestamp()),
        int((pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(VN_TZ).timestamp()),
    )


def fetch_ssi(ticker, start, end, retries=2):
    """Nến ngày từ SSI iBoard. None nếu lỗi/bị chặn, DataFrame rỗng nếu mã không có dữ liệu."""
    frm, to = _range(start, end)
    params = {"resolution": "1D", "symbol": ticker, "from": frm, "to": to}
    for attempt in range(retries):
        try:
            resp = _session.get(SSI_HISTORY_URL, params=params, timeout=30)
            if resp.status_code == 200:
                return parse_ssi(resp.json())
            if resp.status_code in (401, 403, 429):
                return None  # bị chặn: thử lại cũng vô ích
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_vietcap(ticker, start, end, retries=2):
    """Nến ngày từ Vietcap (VCI).

    Vietcap giới hạn theo tần suất gọi: gọi dồn dập sẽ bị từ chối. Vì vậy chờ giữa các lần thử
    và thử lại cả khi bị 429 thay vì bỏ cuộc ngay.
    """
    frm, to = _range(start, end)
    body = {"timeFrame": "ONE_DAY", "symbols": [ticker], "from": frm, "to": to}
    for attempt in range(retries):
        try:
            resp = _session.post(VIETCAP_CHART_URL, json=body, timeout=20)
            if resp.status_code == 200:
                return parse_vietcap(resp.json())
            if resp.status_code in (401, 403):
                return None          # bị chặn hẳn, thử lại vô ích
        except (requests.RequestException, ValueError):
            pass                     # quá hạn / lỗi mạng → nghỉ rồi thử lại
        time.sleep(2 * (attempt + 1))
    return None


# Giãn cách tối thiểu giữa 2 request tới cùng một nguồn (giây).
# Vietcap chặn theo tần suất: gọi dồn dập sẽ bị từ chối, gọi giãn ~0.35s thì ổn định.
MIN_INTERVAL = {"ssi": 0.0, "vietcap": 0.35}
_last_call = {}
_rate_lock = threading.Lock()


def _throttle(name):
    cho = 0.0
    with _rate_lock:
        khoang = MIN_INTERVAL.get(name, 0.0)
        if khoang:
            truoc = _last_call.get(name, 0.0)
            cho = max(0.0, truoc + khoang - time.monotonic())
            _last_call[name] = time.monotonic() + cho
    if cho:
        time.sleep(cho)


def parse_vietcap_batch(payload):
    """Vietcap trả về một mảng cho mỗi mã → tách thành dict mã → DataFrame."""
    ket_qua = {}
    for d in payload if isinstance(payload, list) else []:
        ma = str(d.get("symbol") or "").upper()
        if ma and d.get("t"):
            ket_qua[ma] = _frame_from_arrays(
                d["t"], d.get("o"), d.get("h"), d.get("l"), d.get("c"), d.get("v"), price_divisor=1000.0
            )
    return ket_qua


def fetch_vietcap_batch(tickers, start, end, retries=2):
    """Lấy nhiều mã trong MỘT request (Vietcap nhận danh sách `symbols`).

    Đây là cách tránh bị chặn: nguồn giới hạn theo số lượt gọi, nên 90 mã đi trong 3 lượt
    thay vì 90 lượt. Trả None nếu nguồn không dùng được.
    """
    frm, to = _range(start, end)
    body = {"timeFrame": "ONE_DAY", "symbols": [t.upper() for t in tickers], "from": frm, "to": to}
    for attempt in range(retries):
        try:
            resp = _session.post(VIETCAP_CHART_URL, json=body, timeout=60)
            if resp.status_code == 200:
                return parse_vietcap_batch(resp.json())
            if resp.status_code in (401, 403):
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 * (attempt + 1))
    return None


FETCHERS = {"ssi": fetch_ssi, "vietcap": fetch_vietcap}
SOURCE_ORDER = ("ssi", "vietcap")
_source_stats = {}


def reset_sources():
    with _locks_guard:
        _source_stats.clear()


def source_report():
    with _locks_guard:
        return {k: dict(v) for k, v in _source_stats.items()}


def _usable_sources():
    with _locks_guard:
        stats = {k: dict(v) for k, v in _source_stats.items()}
    ok = [n for n in SOURCE_ORDER if stats.get(n, {}).get("ok")]
    chua_thu = [n for n in SOURCE_ORDER if n not in stats]
    con_lai = [
        n for n in SOURCE_ORDER
        if n in stats and not stats[n].get("ok") and stats[n].get("loi", 0) < MAX_SOURCE_FAILURES
    ]
    return list(dict.fromkeys(ok + chua_thu + con_lai))


def _ghi_nhan(name, thanh_cong):
    with _locks_guard:
        st = _source_stats.setdefault(name, {"ok": 0, "loi": 0})
        st["ok" if thanh_cong else "loi"] += 1


def fetch_auto(ticker, start, end):
    """Thử lần lượt các nguồn còn dùng được; nguồn nào chạy được sẽ được ưu tiên cho mã sau."""
    for name in _usable_sources():
        _throttle(name)
        df = FETCHERS[name](ticker, start, end)
        if df is not None:
            _ghi_nhan(name, True)
            return df
        _ghi_nhan(name, False)
    return None


def path_for(ticker):
    return PRICE_DIR / f"{ticker.upper()}.csv"


def load(ticker):
    path = path_for(ticker)
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["time"])
    return df if not df.empty else None


def _save(ticker, df):
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(path_for(ticker), index=False)


def update_ticker(ticker, session_date=None, fetch=None, history_start=HISTORY_START):
    """Cập nhật một mã. Trả (DataFrame | None, trạng thái)."""
    ticker = ticker.upper()
    fetch = fetch or fetch_auto
    session_date = session_date or last_complete_session()
    today = now_vn().strftime("%Y-%m-%d")
    with _lock_for(ticker):
        current = load(ticker)
        if current is not None and current["time"].max() >= session_date:
            return current, "cached"

        if current is None:
            fresh = fetch(ticker, history_start, today)
            if fresh is None:
                return None, "failed"
            result, status = fresh, "full"
        else:
            last = current["time"].max()
            recent = fetch(ticker, (last - pd.Timedelta(days=OVERLAP_DAYS)).strftime("%Y-%m-%d"), today)
            if recent is None:
                return current, "failed"
            overlap = current.merge(recent, on="time", suffixes=("_old", "_new"))
            drift = (overlap["close_new"] / overlap["close_old"] - 1).abs().max() if len(overlap) else 0.0
            if drift > ADJUST_TOLERANCE:
                full = fetch(ticker, history_start, today)
                if full is None:
                    return current, "failed"
                result, status = full, "readjusted"
            else:
                result = pd.concat([current, recent[recent["time"] > last]], ignore_index=True)
                status = "appended" if (recent["time"] > last).any() else "no_new_data"

        # Không lưu nến phiên chưa đóng cửa
        result = result[result["time"] <= session_date].sort_values("time").reset_index(drop=True)
        if result.empty:
            return None, "empty"
        _save(ticker, result)
        return result, status


def update_many(tickers, workers=4, session_date=None, history_start=HISTORY_START):
    """Cập nhật nhiều mã song song. Trả (dict mã → DataFrame | None, thống kê trạng thái).

    `history_start`: chỉ cần khi tải lần đầu một mã. Đặt gần hiện tại giúp tải nhanh và ít bị
    nguồn từ chối (Smart Money chỉ cần ~400 ngày; pipeline AI mới cần toàn bộ lịch sử).
    """
    session_date = session_date or last_complete_session()
    reset_sources()   # mỗi lần chạy thử lại từ đầu: nguồn hôm qua bị chặn hôm nay có thể dùng được
    tickers = sorted({t.upper() for t in tickers if t})
    han_chot = time.monotonic() + MAX_UPDATE_SECONDS
    prefetched, batch_start = _lay_theo_lo(tickers, session_date, history_start)

    def mot_ma(t):
        if time.monotonic() > han_chot:   # hết giờ: giữ dữ liệu cũ, không để job treo
            return (t, load(t), "qua_gio")
        fetch = _fetch_tu_lo(prefetched[t], batch_start) if t in prefetched else None
        return (t, *update_ticker(t, session_date, fetch=fetch, history_start=history_start))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(mot_ma, tickers))
    frames = {t: df for t, df, _ in results}
    stats = {}
    for t, _, status in results:
        stats.setdefault(status, []).append(t)
    return frames, stats


def _lay_theo_lo(tickers, session_date, history_start):
    """Tải trước theo lô cho các mã còn thiếu ngày. Trả (dict mã → DataFrame, ngày bắt đầu đã yêu cầu)."""
    can_tai, som_nhat = [], None
    for t in tickers:
        cur = load(t)
        if cur is None:
            bat_dau = pd.Timestamp(history_start)
        elif cur["time"].max() < session_date:
            bat_dau = cur["time"].max() - pd.Timedelta(days=OVERLAP_DAYS)
        else:
            continue          # đã đủ dữ liệu, không cần gọi mạng
        can_tai.append(t)
        som_nhat = bat_dau if som_nhat is None else min(som_nhat, bat_dau)

    if not can_tai:
        return {}, None
    ket_qua = {}
    hom_nay = now_vn().strftime("%Y-%m-%d")
    for i in range(0, len(can_tai), BATCH_SIZE):
        lo = can_tai[i:i + BATCH_SIZE]
        _throttle("vietcap")
        data = fetch_vietcap_batch(lo, som_nhat.strftime("%Y-%m-%d"), hom_nay)
        if data is None:      # nguồn không dùng được → quay về tải từng mã
            _ghi_nhan("vietcap", False)
            return ket_qua, som_nhat
        _ghi_nhan("vietcap", True)
        ket_qua.update(data)
    return ket_qua, som_nhat


def _fetch_tu_lo(df_co_san, batch_start):
    """Dùng lại dữ liệu đã tải theo lô; chỉ gọi mạng khi cần khoảng XA HƠN lô đã tải.

    So với `batch_start` (ngày đã yêu cầu khi tải lô) chứ không so với ngày đầu tiên có dữ liệu:
    mã niêm yết muộn vẫn được coi là đã có đủ, không phải gọi lẻ.
    """
    def fetch(ticker, start, end, retries=2):
        if df_co_san is not None and batch_start is not None and pd.Timestamp(start) >= batch_start:
            return df_co_san[df_co_san["time"] >= pd.Timestamp(start)].reset_index(drop=True)
        return fetch_auto(ticker, start, end)
    return fetch


def describe_stats(stats):
    labels = {
        "cached": "đã đủ",
        "appended": "bổ sung ngày thiếu",
        "no_new_data": "không có phiên mới",
        "full": "tải toàn bộ",
        "readjusted": "tải lại do điều chỉnh giá",
        "failed": "lỗi",
        "empty": "không có dữ liệu",
        "qua_gio": "bỏ qua do hết thời gian",
    }
    return ", ".join(f"{labels.get(k, k)} {len(v)}" for k, v in sorted(stats.items()))
