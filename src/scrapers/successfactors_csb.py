"""Adapter cho SAP SuccessFactors — Career Site Builder (CSB), một trong 2 biến
thể SuccessFactors phổ biến. KHÔNG có public JSON API không cần xác thực, nhưng
CSB render bảng job list HTML TĨNH (server-rendered, xác minh trực tiếp trên
jobs.sea.deloitte.com 2026-07) — job detail URL có pattern rõ ràng:
'/job/<slug>/<id_số>/'. Nav link (Show all jobs, Contact us, Privacy,
Cookies...) đều nằm ở path '/go/...' hoặc '/content/...', KHÔNG khớp pattern
này.

2 bước:
  1. "1-hop discovery": trang cấu hình trong config.yaml thường là trang giới
     thiệu (landing), CHƯA phải bảng job list — trang landing có 1 link dạng
     '/go/<slug-chứa-job>/<id_số>/' (vd 'Show all jobs' -> '/go/View-all-Job/
     4636310/') dẫn tới bảng job thật. Ta tìm link này bằng PATTERN URL (không
     dựa vào text hiển thị "Show all jobs" — text đó chính là nav text bị cấm
     ở validation layer, ở đây chỉ dùng để ĐI TỚI trang chứa job, không tạo Job
     object từ chính link đó).
  2. Từ trang job list tìm được, trích job theo pattern strict '/job/.../\\d+/'
     và phân trang theo offset quan sát được ('<root>/<offset>/').
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from heuristics import extract_jobs_by_strict_url_pattern
from http_client import get
from url_utils import normalize_url

JOB_URL_PATTERN = re.compile(r"/job/[^/]+/\d+/?(?:[?#].*)?$", re.IGNORECASE)
LISTING_LINK_PATTERN = re.compile(r"/go/[^/]*job[^/]*/\d+/?(?:[?#].*)?$", re.IGNORECASE)

RECORDS_PER_PAGE = 25
MAX_PAGES = 10


def _find_listing_url(landing_html: str, landing_url: str) -> str:
    """Tìm link 'View all Job'/'Show all jobs' bằng PATTERN URL, không dùng
    text hiển thị (text đó là nav text bị chặn ở validation layer)."""
    soup = BeautifulSoup(landing_html, "lxml")
    for anchor in soup.find_all("a", href=True):
        abs_url = normalize_url(urljoin(landing_url, anchor["href"]))
        if LISTING_LINK_PATTERN.search(abs_url):
            return abs_url
    return ""


def fetch(company: str, params: dict) -> list[dict]:
    landing_url = params["base_url"]

    try:
        landing_html = get(landing_url).text
    except Exception:
        return []

    # Nếu trang landing đã CÓ SẴN job link thật (site nhỏ, không cần trang
    # "view all" riêng) thì dùng luôn, khỏi cần hop thêm 1 request.
    listing_url = landing_url
    listing_html = landing_html
    if not JOB_URL_PATTERN.search(landing_html):
        discovered = _find_listing_url(landing_html, landing_url)
        if not discovered:
            return []
        listing_url = discovered
        try:
            listing_html = get(listing_url).text
        except Exception:
            return []

    all_jobs = []
    seen_urls = set()
    base_path = listing_url.split("?")[0].rstrip("/")

    for page in range(MAX_PAGES):
        if page == 0:
            html, page_url = listing_html, listing_url
        else:
            offset = page * RECORDS_PER_PAGE
            page_url = f"{base_path}/{offset}/"
            try:
                html = get(page_url).text
            except Exception:
                break

        page_jobs = extract_jobs_by_strict_url_pattern(html, page_url, company, JOB_URL_PATTERN)
        new_jobs = [j for j in page_jobs if j["url"] not in seen_urls]
        if not new_jobs:
            break

        for j in new_jobs:
            seen_urls.add(j["url"])
        all_jobs.extend(new_jobs)

        if len(page_jobs) < RECORDS_PER_PAGE // 2:
            break

    return all_jobs
