"""Fallback: dùng Playwright render JS khi html_scraper (requests+BeautifulSoup)
không lấy được job nào — nghĩa là trang thực sự cần JavaScript để render danh sách
(SPA client-side render thuần tuý).

QUAN TRỌNG: dùng CHUNG heuristic `extract_jobs_from_html()` với html_scraper —
không hardcode CSS selector riêng cho từng công ty. Sau khi Playwright render xong,
lấy HTML cuối cùng (page.content()) rồi áp dụng heuristic y hệt lên đó.

Nhiều careers site (Shopee/Zalo/Monee/McKinsey...) chỉ render batch job đầu tiên
sau khi trang load xong, phần còn lại load thêm khi cuộn xuống (infinite scroll)
hoặc bấm "load more". Để xử lý chung cho MỌI site kiểu này mà không cần biết
selector riêng của từng site, sau khi trang load xong ta cuộn xuống đáy nhiều lần
(SCROLL_PASSES) — đây là hành vi generic (giống người dùng thật cuộn trang), áp
dụng được cho bất kỳ site nào dùng infinite scroll, không phải hack riêng cho 1
công ty cụ thể.

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

# Số lần cuộn xuống đáy trang để kích hoạt infinite-scroll/lazy-load — generic,
# áp dụng cho MỌI site, không phải selector riêng cho công ty nào.
SCROLL_PASSES = 4
SCROLL_WAIT_MS = 800


def fetch(url: str, company: str, extra_keywords: tuple = ()) -> list[dict]:
    with PLAYWRIGHT_SEMAPHORE:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_UA)
            try:
                page.goto(url, timeout=45000, wait_until="networkidle")
                # nhiều trang lazy-load list job ngay cả sau networkidle -> đợi thêm 1 nhịp
                page.wait_for_timeout(1500)

                for _ in range(SCROLL_PASSES):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(SCROLL_WAIT_MS)

                html = page.content()
            finally:
                browser.close()

    return extract_jobs_from_html(html, url, company, extra_keywords)
