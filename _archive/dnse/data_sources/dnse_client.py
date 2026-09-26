"""Client đọc dữ liệu thị trường từ DNSE LightSpeed API (OpenAPI).

Tài liệu: https://developers.dnse.com.vn/docs/dnse/market-data
Xác thực: https://developers.dnse.com.vn/docs/guide/intro/authentication
SDK tham chiếu: https://github.com/dnse-tech/openapi-sdk

Module này CHỈ gọi các endpoint đọc dữ liệu thị trường (không đặt lệnh).

Cấu hình qua biến môi trường hoặc file `.env` ở thư mục gốc project:
    DNSE_API_KEY=...
    DNSE_API_SECRET=...
    DNSE_BASE_URL=https://openapi.dnse.com.vn     (tuỳ chọn)
    DNSE_API_VERSION=2026-07-23                    (tuỳ chọn)
    DNSE_DATE_HEADER=Date                          (tuỳ chọn, SDK dùng "Date"; spec ghi "X-Aux-Date")

Lưu ý đơn vị: giá cổ phiếu DNSE trả về theo NGHÌN VND (ví dụ ACB 23.8 = 23.800đ).
"""

import base64
import datetime as dt
import hashlib
import hmac
import os
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://openapi.dnse.com.vn"
DEFAULT_API_VERSION = "2026-07-23"
DEFAULT_DATE_HEADER = "Date"
VN_TZ = "Asia/Ho_Chi_Minh"

INDEX_SYMBOLS = {"VNINDEX", "VN30", "VN100", "HNX", "HNX30", "UPCOM", "VNXALLSHARE"}

# Mỗi request OHLC lấy tối đa khoảng này để tránh response quá lớn
_OHLC_CHUNK_SECONDS = {
    "1D": 365 * 86400,
    "1W": 3 * 365 * 86400,
    "1h": 60 * 86400,
}
_OHLC_CHUNK_INTRADAY_SECONDS = 10 * 86400


class DNSEError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f"DNSE API error {status}: {message}")
        self.status = status


def load_env_file(path=None):
    """Nạp file .env đơn giản (KEY=VALUE). Biến môi trường thật được ưu tiên."""
    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_signature(api_secret, method, path, date_value, nonce, date_header=DEFAULT_DATE_HEADER):
    """HMAC-SHA256(secret, signing string) -> Base64 -> URL-encode (+ / =).

    Signing string (không phụ thuộc query string và body):
        (request-target): get /price/ohlc
        date: Fri, 15 May 2026 07:11:30 +0000
        nonce: c9a8f88b472c9721fde161e0d89df8cc
    """
    header_key = date_header.lower()
    signing_string = f"(request-target): {method.lower()} {path}\n{header_key}: {date_value}"
    if nonce:
        signing_string += f"\nnonce: {nonce}"
    digest = hmac.new(api_secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256).digest()
    encoded = base64.b64encode(digest).decode("utf-8")
    return quote(encoded, safe="")


def _to_unix_seconds(value):
    if value is None:
        return int(time.time())
    if isinstance(value, (int, float)):
        return int(value)
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(VN_TZ)
    return int(ts.timestamp())


class DNSEMarketDataClient:
    def __init__(
        self,
        api_key=None,
        api_secret=None,
        base_url=None,
        api_version=None,
        date_header=None,
        timeout=15,
        max_retries=3,
    ):
        load_env_file()
        self.api_key = api_key or os.getenv("DNSE_API_KEY")
        self.api_secret = api_secret or os.getenv("DNSE_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise DNSEError("CONFIG", "Thiếu DNSE_API_KEY / DNSE_API_SECRET (đặt trong .env hoặc biến môi trường)")
        self.base_url = (base_url or os.getenv("DNSE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_version = api_version or os.getenv("DNSE_API_VERSION") or DEFAULT_API_VERSION
        self.date_header = date_header or os.getenv("DNSE_DATE_HEADER") or DEFAULT_DATE_HEADER
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.rate_limit_remaining = None

    # ------------------------------------------------------------------ core
    def _headers(self, method, path):
        date_value = dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        nonce = uuid.uuid4().hex
        signature = build_signature(self.api_secret, method, path, date_value, nonce, self.date_header)
        return {
            "Accept": "application/json",
            "x-api-key": self.api_key,
            self.date_header: date_value,
            "X-Signature": (
                f'Signature keyId="{self.api_key}",algorithm="hmac-sha256",'
                f'headers="(request-target) {self.date_header.lower()}",'
                f'signature="{signature}",nonce="{nonce}"'
            ),
            "version": self.api_version,
        }

    def request(self, method, path, params=None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base_url}{path}"
        last_error = None
        for attempt in range(self.max_retries + 1):
            # Chữ ký gắn với Date + nonce nên phải tạo mới cho mỗi lần thử
            headers = self._headers(method, path)
            try:
                resp = self.session.request(method, url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = DNSEError("NETWORK", str(exc))
                time.sleep(2 ** attempt)
                continue

            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                try:
                    self.rate_limit_remaining = int(remaining)
                except ValueError:
                    pass

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = DNSEError(resp.status_code, resp.text[:300])
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 5 * (attempt + 1)
                time.sleep(wait)
                continue
            # 4xx khác (sai chữ ký, sai tham số): không retry
            raise DNSEError(resp.status_code, resp.text[:300])
        raise last_error

    # ------------------------------------------------------------ endpoints
    def get_ohlc(self, symbol, start=None, end=None, resolution="1D", market_type=None):
        """Lịch sử nến OHLCV. Trả DataFrame: time, open, high, low, close, volume.

        start/end: unix seconds, datetime, hoặc chuỗi 'YYYY-MM-DD' (giờ VN).
        market_type: STOCK | INDEX | DERIVATIVE (tự đoán nếu bỏ trống).
        """
        symbol = symbol.upper()
        if market_type is None:
            market_type = "INDEX" if symbol in INDEX_SYMBOLS else "STOCK"
        from_ts = _to_unix_seconds(start) if start is not None else int(time.time()) - 365 * 86400
        to_ts = _to_unix_seconds(end)
        chunk = _OHLC_CHUNK_SECONDS.get(resolution, _OHLC_CHUNK_INTRADAY_SECONDS)

        frames = []
        cursor = from_ts
        guard = 0
        while cursor < to_ts and guard < 500:
            guard += 1
            chunk_end = min(cursor + chunk, to_ts)
            payload = self.request(
                "GET",
                "/price/ohlc",
                {"symbol": symbol, "type": market_type, "resolution": resolution, "from": cursor, "to": chunk_end},
            )
            times = payload.get("t") or []
            if times:
                frames.append(
                    pd.DataFrame(
                        {
                            "t": times,
                            "open": payload.get("o"),
                            "high": payload.get("h"),
                            "low": payload.get("l"),
                            "close": payload.get("c"),
                            "volume": payload.get("v"),
                        }
                    )
                )
            next_time = int(payload.get("nextTime") or 0)
            last_t = int(times[-1]) if times else 0
            # nextTime > 0 và nằm trong khoảng hiện tại: server cắt bớt, lấy tiếp từ đó
            if next_time and last_t < next_time < chunk_end:
                cursor = next_time
            else:
                cursor = chunk_end + 1

        columns = ["time", "open", "high", "low", "close", "volume"]
        if not frames:
            return pd.DataFrame(columns=columns)

        df = pd.concat(frames, ignore_index=True).drop_duplicates("t").sort_values("t")
        times = pd.to_datetime(df["t"], unit="s", utc=True).dt.tz_convert(VN_TZ)
        if resolution in ("1D", "1W"):
            df["time"] = times.dt.tz_localize(None).dt.normalize()
        else:
            df["time"] = times.dt.tz_localize(None)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[columns].reset_index(drop=True)

    def get_instruments(self, symbol=None, market_id=None, security_group_id=None, index_name=None, page_size=100):
        """Danh sách mã chứng khoán (tự động phân trang)."""
        rows, page = [], 1
        while True:
            payload = self.request(
                "GET",
                "/market/instruments",
                {
                    "symbol": symbol,
                    "marketId": market_id,
                    "securityGroupId": security_group_id,
                    "indexName": index_name,
                    "limit": page_size,
                    "page": page,
                },
            )
            data = payload.get("data") or []
            rows.extend(data)
            total = int(payload.get("total") or 0)
            if not data or len(rows) >= total or page > 100:
                break
            page += 1
        return pd.DataFrame(rows)

    def get_index_constituents(self, index_name="VN100"):
        """Danh sách mã cổ phiếu thuộc chỉ số (VN30, VN100, HNX30)."""
        df = self.get_instruments(index_name=index_name, security_group_id="ST")
        if df.empty:
            return []
        return sorted(df["symbol"].dropna().astype(str).unique().tolist())

    def get_working_dates(self):
        payload = self.request("GET", "/market/working-dates")
        return pd.to_datetime(payload.get("workingDates") or []).sort_values()

    def get_foreign_trading(self, symbol, start, end, board_id="G1", limit=None):
        """Giao dịch NĐT nước ngoài (khoảng thời gian tối đa 1 ngày mỗi request)."""
        rows, token, guard = [], None, 0
        while guard < 200:
            guard += 1
            payload = self.request(
                "GET",
                f"/price/{symbol.upper()}/foreign-trading",
                {
                    "boardId": board_id,
                    "from": _to_unix_seconds(start),
                    "to": _to_unix_seconds(end),
                    "limit": limit,
                    "nextPageToken": token,
                },
            )
            rows.extend(payload.get("foreigners") or [])
            token = payload.get("nextPageToken")
            if not token:
                break
        return pd.DataFrame(rows)


_default_client = None


def get_default_client():
    """Trả về client dùng chung, hoặc None nếu chưa cấu hình API key."""
    global _default_client
    if _default_client is None:
        try:
            _default_client = DNSEMarketDataClient()
        except DNSEError:
            return None
    return _default_client
