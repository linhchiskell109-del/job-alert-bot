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
         patch("pipeline.is_url_reachable", return_value=True) as mock_reachable, \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        run_for_company(company_cfg)

    mock_nav.assert_called_once()
    call_args = mock_nav.call_args
    assert call_args[0][0] == "https://x.com/landing"  # entry_url đúng
    # is_url_reachable() phải được gọi với URL ĐÃ RESOLVE, không phải entry_url gốc
    mock_reachable.assert_called_once_with("https://x.com/search-results")


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
         patch("pipeline.is_url_reachable", return_value=True) as mock_reachable, \
         patch("pipeline.detect", return_value=__import__("ats_detector").AtsMatch("html", {})), \
         patch("pipeline.html_scraper.fetch", return_value=[]), \
         patch("pipeline.playwright_scraper.fetch", return_value=[]):
        traces, status = run_for_company(company_cfg)

    # KHÔNG return sớm với navigation_failed -- pipeline tiếp tục chạy bình
    # thường bằng final_url thực tế.
    mock_reachable.assert_called_once_with("https://x.com/actual-different-page")
    assert status.method != "navigation_failed"


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
