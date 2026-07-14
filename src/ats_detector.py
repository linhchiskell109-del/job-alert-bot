"""Tự động phát hiện ATS platform (Workday / Greenhouse / Lever) từ URL hoặc HTML —
người dùng KHÔNG cần khai báo thủ công công ty nào dùng nền tảng gì.

Cách hoạt động:
1. Thử match pattern trực tiếp trên URL company (nhanh, không cần tải trang nếu URL
   đã là URL của ATS, vd career page redirect thẳng sang myworkdayjobs.com).
2. Nếu không match, tải HTML trang career và tìm dấu hiệu nhúng ATS (iframe/script
   src trỏ tới greenhouse/lever, hoặc link trực tiếp tới myworkdayjobs.com).
3. Nếu vẫn không phát hiện được -> coi là trang tự build, trả về loại "html" để
   pipeline dùng html_scraper (rồi playwright nếu cần).
"""
import re
from dataclasses import dataclass, field

from http_client import get_safe

WORKDAY_RE = re.compile(
    r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[\w-]+/)?([\w-]+)"
)

GREENHOUSE_PATTERNS = [
    re.compile(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)/jobs"),
    re.compile(r"boards\.greenhouse\.io/([\w-]+)"),
    re.compile(r"greenhouse\.io/embed/job_board\?for=([\w-]+)"),
]

LEVER_PATTERNS = [
    re.compile(r"api\.lever\.co/v0/postings/([\w-]+)"),
    re.compile(r"jobs\.lever\.co/([\w-]+)"),
]


@dataclass
class AtsMatch:
    ats: str                       # "workday" | "greenhouse" | "lever" | "html"
    params: dict = field(default_factory=dict)


def _match_in(text: str):
    m = WORKDAY_RE.search(text)
    if m:
        tenant, wd_number, site = m.groups()
        return AtsMatch("workday", {"tenant": tenant, "wd_number": wd_number, "site": site})

    for pattern in GREENHOUSE_PATTERNS:
        m = pattern.search(text)
        if m:
            return AtsMatch("greenhouse", {"board_token": m.group(1)})

    for pattern in LEVER_PATTERNS:
        m = pattern.search(text)
        if m:
            return AtsMatch("lever", {"company_slug": m.group(1)})

    return None


def detect(url: str) -> AtsMatch:
    direct = _match_in(url)
    if direct:
        return direct

    html = get_safe(url)
    if html:
        detected = _match_in(html)
        if detected:
            return detected

    return AtsMatch("html", {"url": url})
