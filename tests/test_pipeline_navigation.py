"""Test tích hợp Navigation Engine vào pipeline.py — KHÔNG cần browser thật
(mock navigation.navigate) vì mục tiêu là verify pipeline.py GỌI ĐÚNG chỗ,
XỬ LÝ ĐÚNG từng loại lỗi, và KHÔNG đụng gì tới company strategy=direct — hành
vi thật của Navigation Engine đã có tests/test_navigation.py test riêng bằng
browser thật."""
from unittest.mock import patch

from navigation.engine import NavigationResult
from navigation.errors import NavigationFailure, SelectorNotFound, TargetURLMismatch, Timeout
from pipeline import ScrapeStatus, _resolve_entry_url, run_for_company


# ---------------------------------------------------------------------------
# Backward compatibility — direct strategy KHÔNG được đụng tới Navigation Engine
# ---------------------------------------------------------------------------

def test_direct_strategy_never_calls_navigation_engine():
    company_cfg = {"name": "X", "url": "https://x.com/jobs", "strategy": "direct"}
    with patch("pipeline.navigation_navigate") as mock_nav:
        resolved_url, warning, failure = _resolve_entry_url(company_cfg)
    mock_nav.assert_not_called()
    assert resolved_url == "https://x.com/jobs"
    assert warning == "" and failure is None


def test_missing_strategy_defaults_to_direct_bypass():
    company_cfg = {"name": "X", "url": "https://x.com/jobs"}  # không khai báo strategy
    with patch("pipeline.navigation_navigate") as mock_nav:
        resolved_url, warning, failure = _resolve_entry_url(company_cfg)
    mock_nav.assert_not_called()
    assert resolved_url == "https://x.com/jobs"


def test_run_for_company_direct_strategy_unaffected_end_to_end():
    """Company strategy=direct chạy qua run_for_company() PHẢI cho kết quả
    giống hệt trước khi có Navigation Engine — không gọi navigate() ở đâu cả."""
    company_cfg = {"name": "X", "url": "https://x.com/jobs", "strategy": "direct"}
    with patch("pipeline.navigation_navigate") as mock_nav, \
         patch("pipeline.is_url_reachable", return_value=True), \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        run_for_company(company_cfg)
    mock_nav.assert_not_called()


# ---------------------------------------------------------------------------
# Landing strategy — navigation chạy, URL đã resolve được dùng cho phần còn lại
# ---------------------------------------------------------------------------

def test_landing_strategy_resolves_url_before_ats_detect():
    company_cfg = {
        "name": "X", "url": "https://x.com/landing", "strategy": "landing",
        "navigation": [{"click_text": "Search"}], "target_url": "https://x.com/search-results",
    }
    fake_result = NavigationResult(final_url="https://x.com/search-results", logs=["ok"])
    with patch("pipeline.navigation_navigate", return_value=fake_result) as mock_nav, \
         patch("pipeline.is_url_reachable") as mock_reachable, \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        run_for_company(company_cfg)

    mock_nav.assert_called_once()
    call_args = mock_nav.call_args
    assert call_args[0][0] == "https://x.com/landing"  # entry_url đúng
    # Navigation Engine đã chứng minh URL load được bằng browser thật -> KHÔNG
    # kiểm tra lại bằng request HTTP thuần (bug thật đã xảy ra với PwC: navigate
    # thành công nhưng is_url_reachable() sau đó lại báo sai UNREACHABLE).
    mock_reachable.assert_not_called()


# ---------------------------------------------------------------------------
# Lỗi navigation — phân loại RÕ RÀNG, không gộp chung UNREACHABLE
# ---------------------------------------------------------------------------

def test_selector_not_found_produces_distinct_scrape_status():
    company_cfg = {"name": "X", "url": "https://x.com/landing", "strategy": "landing",
                    "navigation": [{"click_css": "#missing"}]}
    with patch("pipeline.navigation_navigate", side_effect=SelectorNotFound("khong tim thay #missing")):
        traces, status = run_for_company(company_cfg)
    assert traces == []
    assert status.method == "navigation_failed"
    assert not status.ok
    assert "SelectorNotFound" in status.detail


def test_timeout_produces_distinct_scrape_status():
    company_cfg = {"name": "X", "url": "https://x.com/landing", "strategy": "landing",
                    "navigation": [{"wait_networkidle": {}}]}
    with patch("pipeline.navigation_navigate", side_effect=Timeout("het thoi gian cho")):
        traces, status = run_for_company(company_cfg)
    assert status.method == "navigation_failed"
    assert "Timeout" in status.detail


def test_generic_navigation_failure_produces_distinct_scrape_status():
    company_cfg = {"name": "X", "url": "https://x.com/landing", "strategy": "landing", "navigation": []}
    with patch("pipeline.navigation_navigate", side_effect=NavigationFailure("browser crash")):
        traces, status = run_for_company(company_cfg)
    assert status.method == "navigation_failed"
    assert "NavigationFailure" in status.detail


def test_navigation_errors_never_labeled_as_generic_unreachable():
    company_cfg = {"name": "X", "url": "https://x.com/landing", "strategy": "landing", "navigation": []}
    for error in (SelectorNotFound("x"), Timeout("x"), NavigationFailure("x")):
        with patch("pipeline.navigation_navigate", side_effect=error):
            _, status = run_for_company(company_cfg)
        assert status.method != "unreachable"


# ---------------------------------------------------------------------------
# TargetURLMismatch — KHÔNG fatal, vẫn dùng final_url thực tế
# ---------------------------------------------------------------------------

def test_target_url_mismatch_is_not_fatal_and_uses_real_final_url():
    company_cfg = {
        "name": "X", "url": "https://x.com/landing", "strategy": "landing",
        "navigation": [{"click_text": "Search"}], "target_url": "https://x.com/expected",
    }
    mismatch = TargetURLMismatch("URL lech", final_url="https://x.com/actual-different-page")
    with patch("pipeline.navigation_navigate", side_effect=mismatch), \
         patch("pipeline.is_url_reachable") as mock_reachable, \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[{"title": "Business Analyst", "url": "https://x.com/actual-different-page/j1", "location": "Hanoi"}]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        traces, status = run_for_company(company_cfg)

    # KHÔNG return sớm với navigation_failed -- pipeline tiếp tục chạy bình
    # thường bằng final_url thực tế, và KHÔNG gọi lại is_url_reachable (đã
    # được Navigation Engine chứng minh load được).
    mock_reachable.assert_not_called()
    assert status.method != "navigation_failed"
    assert len(traces) == 1


# ---------------------------------------------------------------------------
# navigation_retries override từ config.yaml được truyền đúng xuống engine
# ---------------------------------------------------------------------------

def test_navigation_retries_config_override_is_passed_through():
    company_cfg = {"name": "X", "url": "https://x.com/landing", "strategy": "landing",
                    "navigation": [{"click_text": "Search"}], "navigation_retries": 5}
    fake_result = NavigationResult(final_url="https://x.com/ok", logs=[])
    with patch("pipeline.navigation_navigate", return_value=fake_result) as mock_nav:
        _resolve_entry_url(company_cfg)
    assert mock_nav.call_args.kwargs.get("retries") == 5


def test_direct_strategy_still_performs_reachability_check_unaffected():
    """Company strategy=direct KHÔNG có navigation chứng minh URL load được ->
    vẫn PHẢI giữ nguyên hành vi is_url_reachable() như trước (backward compat)."""
    company_cfg = {"name": "X", "url": "https://x.com/jobs", "strategy": "direct"}
    with patch("pipeline.is_url_reachable", return_value=False) as mock_reachable:
        traces, status = run_for_company(company_cfg)
    mock_reachable.assert_called_once_with("https://x.com/jobs")
    assert status.method == "unreachable"


def test_pwc_style_bug_navigation_success_never_gets_marked_unreachable():
    """Regression test cho bug thực tế: PwC navigate() thành công (browser thật
    load được trang), nhưng is_url_reachable() (request HTTP thuần) sau đó lại
    báo sai UNREACHABLE vì site chặn request không có cookie/session/UA mà
    browser vừa có. Fix: bỏ qua is_url_reachable() hoàn toàn khi navigation đã
    tự chứng minh URL load được."""
    company_cfg = {
        "name": "PwC Vietnam", "url": "https://www.pwc.com/vn/en/careers.html", "strategy": "landing",
        "navigation": [{"click_text": "Experienced Professionals"}],
        "target_url": "https://www.pwc.com/vn/en/careers/experienced-jobs.html",
    }
    fake_result = NavigationResult(final_url="https://www.pwc.com/vn/en/careers/experienced-jobs.html", logs=[])
    with patch("pipeline.navigation_navigate", return_value=fake_result), \
         patch("pipeline.is_url_reachable", return_value=False) as mock_reachable, \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        traces, status = run_for_company(company_cfg)

    mock_reachable.assert_not_called()  # không được gọi -> không thể bị báo sai unreachable
    assert status.method != "unreachable"
