"""Adapter cho ATS Avature — KHÔNG có public JSON API tài liệu hoá, nhưng trang
job list là HTML TĨNH (server-rendered, không cần JS) với URL job detail có
pattern RÕ RÀNG và ổn định: '/jobs/FolderDetail/<slug>/<id_số>'. Đây là dấu
hiệu mạnh để phân biệt job THẬT với nav link (nav link không có ID số ở cuối) —
xác minh trực tiếp trên careers.bain.com/jobs (2026-07): mọi job card đều theo
đúng pattern này, mọi nav link (Search jobs/Register/Login/Learn more/Share
this job/Terms & conditions...) đều KHÔNG khớp.

Nhận diện Avature qua meta tag 'avature.portal.*' trong HTML (xem
ats_detector.py) — hoạt động cả khi site KHÔNG có 'avature' trong domain (vd
careers.bain.com), vì Avature là platform trắng nhãn (white-label).

Phân trang: trang gốc (`base_url`, offset 0) đã chứa 10 job đầu; các trang sau
theo pattern '<root>/SearchJobs/?folderRecordsPerPage=N&folderOffset=M' (quan
sát trực tiếp từ link phân trang trên trang Bain).
"""
import re

from heuristics import extract_jobs_by_strict_url_pattern
from http_client import get

JOB_URL_PATTERN = re.compile(r"/jobs/FolderDetail/[^/]+/\d+/?(?:[?#].*)?$", re.IGNORECASE)

RECORDS_PER_PAGE = 50
MAX_PAGES = 10  # an toàn: tối đa 500 job/lần chạy, đủ cho mọi công ty thực tế


def _search_jobs_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.lower().endswith("/searchjobs"):
        root = root[: -len("/SearchJobs")]
    return root


def fetch(company: str, params: dict) -> list[dict]:
    base_url = params["base_url"]
    root = _search_jobs_root(base_url)

    all_jobs = []
    seen_urls = set()

    for page in range(MAX_PAGES):
        offset = page * RECORDS_PER_PAGE
        page_url = f"{root}/SearchJobs/?folderRecordsPerPage={RECORDS_PER_PAGE}&folderOffset={offset}"
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

        if len(page_jobs) < RECORDS_PER_PAGE // 2:  # trang gần cuối, dừng sớm cho đỡ tốn request
            break

    return all_jobs
