"""Tiện ích xử lý URL:
1. normalize_url() — bỏ tracking query param (utm_*, fbclid, gclid, srsltid...)
   trước khi lưu/dùng URL, giữ nguyên các param thật sự cần thiết (vd ?locale=vi_VN).
2. is_url_reachable() — kiểm tra 1 URL có thực sự truy cập được không, dùng để
   quyết định BỎ QUA 1 công ty ngay từ đầu thay vì chạy hết cả pipeline rồi mới
   phát hiện URL chết. KHÔNG BAO GIỜ tự đoán/tạo URL thay thế khi 1 URL không
   truy cập được — chỉ log cảnh báo và bỏ qua công ty đó.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from http_client import get

_TRACKING_PARAM_PATTERNS = (
    re.compile(r"^utm_"),
    re.compile(r"^fbclid$"),
    re.compile(r"^gclid$"),
    re.compile(r"^gclsrc$"),
    re.compile(r"^srsltid$"),
    re.compile(r"^mc_cid$"),
    re.compile(r"^mc_eid$"),
    re.compile(r"^igshid$"),
    re.compile(r"^_hs(enc|mi)$"),
    re.compile(r"^ref$"),
)


def _is_tracking_param(key: str) -> bool:
    key_lower = key.lower()
    return any(p.match(key_lower) for p in _TRACKING_PARAM_PATTERNS)


def normalize_url(url: str) -> str:
    """Bỏ tracking param + fragment (#...), giữ nguyên param cần thiết cho chức
    năng của trang (vd ?locale=vi_VN, ?id=123)."""
    if not url:
        return url

    parts = urlsplit(url.strip())
    kept_params = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    ]
    new_query = urlencode(kept_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, ""))


def is_url_reachable(url: str) -> bool:
    """True nếu URL trả về response (status < 400). Không raise exception —
    mọi lỗi mạng/DNS/timeout đều coi là 'không truy cập được'."""
    try:
        return get(url).status_code < 400
    except Exception:
        return False
