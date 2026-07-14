"""HTTP client dùng chung cho TOÀN BỘ network request trong project.
Mọi adapter (workday/greenhouse/lever/html_scraper/ats_detector) đều gọi qua module
này để có retry với exponential backoff tự động khi gặp lỗi mạng / 429 / 5xx.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobAlertBot/2.0"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _build_session(total_retries: int = 4, backoff_factor: float = 1.5) -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff_factor,           # sleep: 0s, 1.5s, 3s, 6s, 12s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# 1 session dùng chung cho cả process — requests.Session an toàn khi dùng từ nhiều
# thread cùng lúc (mỗi request tạo connection riêng từ pool).
SESSION = _build_session()


def get(url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", 20)
    resp = SESSION.get(url, **kwargs)
    resp.raise_for_status()
    return resp


def post(url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", 20)
    resp = SESSION.post(url, **kwargs)
    resp.raise_for_status()
    return resp


def get_safe(url: str, **kwargs) -> str:
    """Như get() nhưng không raise nếu lỗi — trả về '' (dùng cho ATS auto-detect,
    nơi 1 request thất bại không nên làm sập toàn bộ pipeline)."""
    try:
        return get(url, **kwargs).text
    except Exception:
        return ""
