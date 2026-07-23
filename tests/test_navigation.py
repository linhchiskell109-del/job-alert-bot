"""Test Navigation Engine bằng browser THẬT (headless Chromium, không cần
mạng — chạy trên file:// fixture cục bộ trong tests/fixtures/navigation/) cho
các case cần tính chân thực (selector tồn tại/không tồn tại, timeout do bị che
pointer-events, redirect, final_url) — và mock cho các case cần tính xác định
cao (đếm số lần retry, format log) mà không phụ thuộc thời gian browser thật.
"""
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from navigation.engine import NavigationResult, navigate
from navigation.errors import NavigationFailure, SelectorNotFound, TargetURLMismatch, Timeout

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "navigation"


def _file_url(name: str) -> str:
    return FIXTURES_DIR.joinpath(name).as_uri()


# ---------------------------------------------------------------------------
# Real-browser integration tests
# ---------------------------------------------------------------------------

def test_successful_navigation_resolves_final_url():
    entry = _file_url("landing.html")
    target = _file_url("target.html")
    result = navigate(entry, [{"click_text": "Search jobs"}], target_url=target)
    assert result.final_url == target
    assert result.page is None and result.browser is None  # đóng session mặc định


def test_selector_not_found_raises_immediately_without_long_retry():
    entry = _file_url("landing.html")
    start = time.time()
    with pytest.raises(SelectorNotFound):
        navigate(entry, [{"click_css": "#this-selector-does-not-exist"}],
                 retries=3, page_timeout_ms=5000)
    elapsed = time.time() - start
    # SelectorNotFound KHÔNG được retry -> chỉ tốn đúng 1 lần exist-check
    # (mặc định 8s), không cộng dồn thời gian của 3 lần retry.
    assert elapsed < 12


def test_timeout_when_element_exists_but_blocked_by_overlay():
    entry = _file_url("landing.html")
    with pytest.raises(Timeout):
        navigate(entry, [{"click_css": {"selector": "#blocked-btn", "timeout_ms": 1000}}],
                 retries=0, page_timeout_ms=5000)


def test_redirected_url_is_captured_as_final_url():
    entry = _file_url("landing.html")
    target = _file_url("target.html")
    # Chỉnh landing.html để có link dẫn thẳng qua target (đã có #search-link)
    result = navigate(entry, [{"click_text": "Search jobs"}, {"wait_networkidle": {}}], target_url=target)
    assert result.final_url == target


def test_navigation_logs_contain_step_numbers_and_final_url():
    entry = _file_url("landing.html")
    result = navigate(entry, [{"click_text": "Search jobs"}])
    joined = "\n".join(result.logs)
    assert "Step 1/1" in joined
    assert 'click_text("Search jobs")' in joined
    assert "✓ Success" in joined
    assert "Final URL:" in joined


def test_keep_session_returns_live_page_for_future_parsers():
    entry = _file_url("landing.html")
    result = navigate(entry, [{"click_text": "Search jobs"}], keep_session=True)
    try:
        assert result.page is not None
        assert result.browser_context is not None
        assert result.browser is not None
        assert result.page.url == result.final_url
    finally:
        result.close()


def test_target_url_mismatch_raised_when_final_url_differs():
    entry = _file_url("landing.html")
    wrong_target = _file_url("does-not-match.html")
    with pytest.raises(TargetURLMismatch):
        navigate(entry, [{"click_text": "Search jobs"}], target_url=wrong_target)


# ---------------------------------------------------------------------------
# Direct-page smoke test (no navigation config at all — entry itself is final)
# ---------------------------------------------------------------------------

def test_landing_page_with_no_steps_returns_entry_url_unchanged():
    entry = _file_url("target.html")
    result = navigate(entry, [])
    assert result.final_url == entry


# ---------------------------------------------------------------------------
# Retry logic — mocked (deterministic, no real browser timing dependency)
# ---------------------------------------------------------------------------

def test_retry_logic_retries_transient_failures_up_to_limit():
    calls = {"n": 0}

    def fake_run_steps_once(entry_url, steps, target_url, keep_session, page_timeout_ms, log):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Timeout("simulated transient timeout")
        return NavigationResult(final_url="https://x.com/ok", logs=["ok"])

    with patch("navigation.engine._run_steps_once", fake_run_steps_once), \
         patch("navigation.engine.time.sleep", lambda s: None):
        result = navigate("https://x.com/entry", [{"wait_timeout": 100}], retries=3)

    assert calls["n"] == 3
    assert result.final_url == "https://x.com/ok"


def test_retry_logic_gives_up_after_max_retries():
    def always_fails(entry_url, steps, target_url, keep_session, page_timeout_ms, log):
        raise Timeout("always fails")

    with patch("navigation.engine._run_steps_once", always_fails), \
         patch("navigation.engine.time.sleep", lambda s: None):
        with pytest.raises(Timeout):
            navigate("https://x.com/entry", [{"wait_timeout": 100}], retries=2)


def test_retry_logic_never_retries_selector_not_found():
    calls = {"n": 0}

    def fake_run_steps_once(entry_url, steps, target_url, keep_session, page_timeout_ms, log):
        calls["n"] += 1
        raise SelectorNotFound("selector missing")

    with patch("navigation.engine._run_steps_once", fake_run_steps_once), \
         patch("navigation.engine.time.sleep", lambda s: None):
        with pytest.raises(SelectorNotFound):
            navigate("https://x.com/entry", [{"click_css": "#x"}], retries=3)

    assert calls["n"] == 1  # KHÔNG retry


def test_retry_logic_never_retries_target_url_mismatch():
    calls = {"n": 0}

    def fake_run_steps_once(entry_url, steps, target_url, keep_session, page_timeout_ms, log):
        calls["n"] += 1
        raise TargetURLMismatch("mismatch")

    with patch("navigation.engine._run_steps_once", fake_run_steps_once), \
         patch("navigation.engine.time.sleep", lambda s: None):
        with pytest.raises(TargetURLMismatch):
            navigate("https://x.com/entry", [{"click_text": "x"}], target_url="https://x.com/y", retries=3)

    assert calls["n"] == 1
