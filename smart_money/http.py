import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import HEADERS, HTTP_WORKERS


def make_session(retries=3, backoff=0.8):
    """Session dùng chung: retry khi lỗi mạng / 429 / 5xx, tái sử dụng kết nối."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "PUT"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=HTTP_WORKERS * 2, pool_maxsize=HTTP_WORKERS * 2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session
