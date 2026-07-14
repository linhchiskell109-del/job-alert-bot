"""Fallback: dùng Playwright render JS khi html_scraper (requests+BeautifulSoup)
không lấy được job nào — nghĩa là trang thực sự cần JavaScript để render danh sách
(SPA client-side render thuần tuý).

QUAN TRỌNG: dùng CHUNG heuristic `extract_jobs_from_html()` với html_scraper —
không hardcode CSS selector riêng cho từng công ty. Sau khi Playwright render xong,
lấy HTML cuối cùng (page.content()) rồi áp dụng heuristic y hệt lên đó.

Lưu ý kỹ thuật: mỗi lần gọi fetch() tự tạo 1 `sync_playwright()` instance riêng
(không chia sẻ giữa các thread) — an toàn khi chạy trong ThreadPoolExecutor, đúng
theo khuyến nghị của Playwright cho môi trường đa luồng. Số browser chạy đồng thời
bị giới hạn bởi PLAYWRIGHT_SEMAPHORE (xem concurrency.py) để tránh quá tải runner.
"""
from playwright.sync_api import sync_playwright

from concurrency import PLAYWRIGHT_SEMAPHORE
from heuristics import extract_jobs_from_html

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobAlertBot/2.0"
)


def fetch(url: str, company: str, extra_keywords: tuple = ()) -> list[dict]:
    with PLAYWRIGHT_SEMAPHORE:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_UA)
            try:
                page.goto(url, timeout=45000, wait_until="networkidle")
                # nhiều trang lazy-load list job ngay cả sau networkidle -> đợi thêm 1 nhịp
                page.wait_for_timeout(1500)
                html = page.content()
            finally:
                browser.close()

    return extract_jobs_from_html(html, url, company, extra_keywords)
