"""Regression test cho fix BCG (audit): playwright_scraper.py trước đây dùng
wait_until="networkidle", treo vô thời hạn trên site có network activity liên
tục (chat widget/analytics polling — chính xác kiểu site Phenom People như
BCG). Test dựng 1 HTTP server cục bộ THẬT có endpoint poll liên tục (không
phải mock) để tái hiện đúng lỗi, rồi xác nhận playwright_scraper.fetch() (đã
đổi sang domcontentloaded) không bị treo."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scrapers import playwright_scraper

_HTML = b"""<!DOCTYPE html><html><body>
<div class="job-card"><a href="/jobs/12345">Business Analyst</a></div>
<script>
setInterval(function() { fetch('/poll?t=' + Date.now()); }, 200);
</script>
</body></html>"""


class _PollingHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/poll"):
            time.sleep(2)  # endpoint chậm -> giữ 1 connection "in flight" quá cửa sổ 500ms của networkidle
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_HTML if self.path == "/" else b"ok")
        except (BrokenPipeError, ConnectionResetError):
            pass  # client (browser) có thể đã đóng connection trước khi server kịp trả lời


@pytest.fixture
def polling_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PollingHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/"
    server.shutdown()


def test_playwright_scraper_does_not_hang_on_persistent_network_activity(polling_server):
    """Regression test cho bug BCG: trước đây (wait_until='networkidle') lệnh
    này sẽ TIMEOUT/treo vì server liên tục có request 'poll' đang chạy. Sau
    khi đổi sang 'domcontentloaded', fetch() phải hoàn tất nhanh và vẫn lấy
    được job từ HTML tĩnh ban đầu."""
    start = time.time()
    jobs = playwright_scraper.fetch(polling_server, "TestCo")
    elapsed = time.time() - start

    assert elapsed < 15  # với networkidle cũ, việc này sẽ mất tới 45s (page_timeout) rồi lỗi
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Business Analyst"
