from job_trace import JobTrace, TERMINAL_STATUSES, extraction_confidence, match_reason_to_status


def test_new_trace_is_not_terminal():
    trace = JobTrace(company="X", title="Business Analyst")
    assert not trace.is_terminal
    assert trace.status == "CRAWLED"


def test_set_status_to_terminal_marks_is_terminal():
    trace = JobTrace(company="X", title="Business Analyst")
    trace.set_status("REJECTED_LOCATION", "location=Singapore")
    assert trace.is_terminal
    assert trace.status == "REJECTED_LOCATION"
    assert trace.detail == "location=Singapore"


def test_history_tracks_every_status_transition():
    trace = JobTrace(company="X", title="Business Analyst")
    trace.set_status("NORMALIZED")
    trace.set_status("NOTIFIED", "job moi")
    assert trace.history == ["CRAWLED", "NORMALIZED", "NOTIFIED"]


def test_all_terminal_statuses_are_actually_terminal():
    for status in TERMINAL_STATUSES:
        trace = JobTrace(company="X", title="Y")
        trace.set_status(status)
        assert trace.is_terminal


def test_match_reason_maps_to_expected_status():
    assert match_reason_to_status("excluded_function") == "REJECTED_FUNCTION"
    assert match_reason_to_status("keyword") == "REJECTED_FUNCTION"
    assert match_reason_to_status("experience") == "REJECTED_EXPERIENCE"
    assert match_reason_to_status("score_too_low") == "REJECTED_SCORE"
    assert match_reason_to_status("location") == "REJECTED_LOCATION"


def test_extraction_confidence_full_when_all_fields_present():
    job = {"title": "Business Analyst", "location": "Hanoi", "department": "Strategy", "employment_type": "Full-time"}
    assert extraction_confidence(job) == 1.0


def test_extraction_confidence_penalizes_unknown_location():
    job = {"title": "Business Analyst", "location": "Unknown", "department": "Strategy", "employment_type": "Full-time"}
    assert extraction_confidence(job) < 1.0


def test_extraction_confidence_penalizes_missing_fields():
    job = {"title": "Business Analyst", "location": "", "department": "", "employment_type": ""}
    conf = extraction_confidence(job)
    assert 0 < conf < 1.0
