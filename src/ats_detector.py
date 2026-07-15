"""Tự động phát hiện ATS platform từ URL hoặc HTML — người dùng KHÔNG cần khai báo
thủ công công ty nào dùng nền tảng gì.

Hỗ trợ nhận diện: Workday, Greenhouse, Lever, SmartRecruiters (có adapter public
API riêng — xem scrapers/), và SAP SuccessFactors, Oracle Recruiting Cloud (chỉ
NHẬN DIỆN để log/route đúng hướng — 2 nền tảng này không có API JSON công khai ổn
định không cần xác thực, nên pipeline sẽ route sang html_scraper/playwright thay
vì cố gọi API).

Cách hoạt động:
1. Thử match pattern trực tiếp trên URL company (nhanh, không cần tải trang nếu
   URL đã là URL của ATS, vd career page redirect thẳng sang myworkdayjobs.com).
2. Nếu không match, tải HTML trang career và tìm dấu hiệu nhúng ATS (iframe/script
   src trỏ tới greenhouse/lever/smartrecruiters/successfactors/oracle, hoặc link
   trực tiếp tới domain ATS đó).
3. Nếu vẫn không phát hiện được -> coi là trang tự build, trả về loại "html" để
   pipeline dùng html_scraper (rồi playwright nếu cần).

KHÔNG BAO GIỜ tự đoán/tạo tenant, board token, hay domain — mọi params đều được
trích xuất trực tiếp từ URL/HTML thật sự quan sát được, không suy đoán.
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

SMARTRECRUITERS_PATTERNS = [
    re.compile(r"api\.smartrecruiters\.com/v1/companies/([\w-]+)/postings"),
    re.compile(r"careers\.smartrecruiters\.com/([\w-]+)"),
    re.compile(r"jobs\.smartrecruiters\.com/([\w-]+)"),
]

# SAP SuccessFactors (Career Site Builder) và Oracle Recruiting Cloud không có API
# JSON công khai ổn định (không cần xác thực) theo hiểu biết hiện tại — nên chỉ
# nhận diện để LOG cho đúng, không có adapter riêng. Pipeline tự route các ATS
# này sang html_scraper/playwright.
SUCCESSFACTORS_PATTERN = re.compile(
    r"successfactors\.com|career_ns=job_listing|sfcareersite|universalcareersite",
    re.IGNORECASE,
)

ORACLE_RECRUITING_PATTERNS = [
    re.compile(r"[\w-]+\.fa\.[\w-]+\.oraclecloud\.com/hcmUI/CandidateExperience", re.IGNORECASE),
    re.compile(r"eeho\.fa\.[\w-]+\.oraclecloud\.com", re.IGNORECASE),
]

# ATS có adapter public API riêng (xem pipeline.ATS_ADAPTERS)
ADAPTER_SUPPORTED_ATS = {"workday", "greenhouse", "lever", "smartrecruiters"}
# ATS nhận diện được nhưng KHÔNG có adapter public API -> route sang html/playwright
DETECTED_ONLY_ATS = {"successfactors", "oracle_recruiting"}


@dataclass
class AtsMatch:
    ats: str                       # "workday" | "greenhouse" | "lever" | "smartrecruiters"
                                    # | "successfactors" | "oracle_recruiting" | "html"
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

    for pattern in SMARTRECRUITERS_PATTERNS:
        m = pattern.search(text)
        if m:
            return AtsMatch("smartrecruiters", {"company_identifier": m.group(1)})

    for pattern in ORACLE_RECRUITING_PATTERNS:
        if pattern.search(text):
            return AtsMatch("oracle_recruiting", {})

    if SUCCESSFACTORS_PATTERN.search(text):
        return AtsMatch("successfactors", {})

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
