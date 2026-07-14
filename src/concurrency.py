"""Giới hạn số browser Playwright chạy đồng thời — tránh mở quá nhiều Chromium
cùng lúc khi fetch nhiều công ty song song (tốn RAM/CPU, dễ làm GitHub Actions
runner quá tải)."""
import os
import threading

PLAYWRIGHT_MAX_CONCURRENCY = int(os.environ.get("PLAYWRIGHT_MAX_CONCURRENCY", "2"))
PLAYWRIGHT_SEMAPHORE = threading.Semaphore(PLAYWRIGHT_MAX_CONCURRENCY)
