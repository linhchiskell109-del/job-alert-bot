from pipeline import _trace_raw_jobs


def test_every_raw_job_produces_exactly_one_trace():
    raw = [
        {"title": "Business Analyst", "url": "https://x.com/1", "location": "Hanoi"},
        {"title": "Explore", "url": "https://x.com/careers/explore", "location": ""},  # nav page
        {"title": "Business Analyst", "url": "https://x.com/2", "location": "Singapore"},  # foreign
    ]
    traces = _trace_raw_jobs(raw, "TestCo", ("vietnam", "hanoi"))
    assert len(traces) == len(raw)  # KHÔNG job nào biến mất


def test_nav_page_gets_rejected_validation_status():
    raw = [{"title": "Explore", "url": "https://x.com/careers/explore", "location": "Hanoi"}]
    traces = _trace_raw_jobs(raw, "TestCo", ())
    assert traces[0].status == "REJECTED_VALIDATION"
    assert traces[0].is_terminal


def test_foreign_location_gets_rejected_location_status():
    raw = [{"title": "Business Analyst", "url": "https://x.com/1", "location": "Singapore"}]
    traces = _trace_raw_jobs(raw, "TestCo", ("vietnam", "hanoi"))
    assert traces[0].status == "REJECTED_LOCATION"
    assert traces[0].is_terminal


def test_valid_job_stays_non_terminal_ready_for_matching():
    raw = [{"title": "Business Analyst", "url": "https://x.com/1", "location": "Hanoi"}]
    traces = _trace_raw_jobs(raw, "TestCo", ("vietnam", "hanoi"))
    assert traces[0].status == "NORMALIZED"
    assert not traces[0].is_terminal
    assert traces[0].job is not None


def test_trace_job_is_always_populated_even_when_rejected():
    # Cho phép shared portal phân loại brand ngay cả với trace bị reject.
    raw = [{"title": "Explore", "url": "https://x.com/careers/explore", "location": ""}]
    traces = _trace_raw_jobs(raw, "TestCo", ())
    assert traces[0].job is not None
