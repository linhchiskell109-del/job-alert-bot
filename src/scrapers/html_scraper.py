"""Scraper HTML tĩnh (requests + BeautifulSoup) — LỰA CHỌN ĐẦU TIÊN cho mọi công ty
không dùng ATS đã biết (Workday/Greenhouse/Lever).

Nhiều trang career hiện đại — kể cả app Next.js/Nuxt — render sẵn danh sách job
trong HTML trả về từ server (SSR/SSG), nên không cần trình duyệt thật để lấy dữ
liệu. Cách này nhanh hơn Playwright nhiều lần và không tốn tài nguyên chạy Chromium.
Chỉ khi cách này lấy được 0 job (trang thực sự cần JS để render list) thì pipeline
mới fallback sang playwright_scraper.
"""
from http_client import get
from heuristics import extract_jobs_from_html


def fetch(url: str, company: str, extra_keywords: tuple = ()) -> list[dict]:
    html = get(url).text
    return extract_jobs_from_html(html, url, company, extra_keywords)
