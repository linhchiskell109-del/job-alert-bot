from diagnostics import Diagnostics
from job_trace import JobTrace
from pipeline import ScrapeStatus


def _make_trace(company, title, status, detail=""):
    t = JobTrace(company=company, title=title, url="https://x.com/1", job={"title": title, "location": "Hanoi"})
    t.set_status(status, detail)
    return t


def test_funnel_counts_by_stage():
    diag = Diagnostics()
    diag.add_scrape_status("Grab", ScrapeStatus("html", ok=True, raw_count=4))
    diag.add_traces([
        _make_trace("Grab", "A", "NOTIFIED"),
        _make_trace("Grab", "B", "ALREADY_NOTIFIED"),
        _make_trace("Grab", "C", "REJECTED_FUNCTION"),
        _make_trace("Grab", "D", "REJECTED_VALIDATION"),
    ])
    funnel = diag.funnel_for("Grab")
    assert funnel["raw"] == 4
    assert funnel["validated"] == 3  # 4 - 1 REJECTED_VALIDATION
    assert funnel["matched"] == 2    # NOTIFIED + ALREADY_NOTIFIED
    assert funnel["already_notified"] == 1
    assert funnel["new_notifications"] == 1


def test_rejection_breakdown_groups_by_reason():
    diag = Diagnostics()
    diag.add_traces([
        _make_trace("Grab", "A", "REJECTED_LOCATION"),
        _make_trace("Grab", "B", "REJECTED_LOCATION"),
        _make_trace("Grab", "C", "REJECTED_EXPERIENCE"),
        _make_trace("Grab", "D", "ALREADY_NOTIFIED"),
    ])
    breakdown = diag.rejection_breakdown_for("Grab")
    assert breakdown["location"] == 2
    assert breakdown["experience"] == 1
    assert breakdown["duplicate"] == 1


def test_conservation_holds_when_every_trace_is_terminal():
    diag = Diagnostics()
    diag.add_traces([
        _make_trace("Grab", "A", "NOTIFIED"),
        _make_trace("Grab", "B", "REJECTED_SCORE"),
    ])
    ok, message = diag.verify_conservation()
    assert ok
    assert "2/2" in message


def test_conservation_fails_when_a_trace_is_left_non_terminal():
    diag = Diagnostics()
    stuck = JobTrace(company="Grab", title="Stuck job")  # chưa set_status -> vẫn CRAWLED
    diag.add_traces([stuck])
    ok, message = diag.verify_conservation()
    assert not ok
    assert "VI PHẠM" in message


def test_accepted_jobs_always_listed_even_when_already_notified():
    diag = Diagnostics()
    diag.add_traces([
        _make_trace("Grab", "Old job", "ALREADY_NOTIFIED"),
        _make_trace("Grab", "New job", "NOTIFIED"),
        _make_trace("Grab", "Rejected job", "REJECTED_FUNCTION"),
    ])
    accepted_titles = [t.title for t in diag.traces if t.status in ("NOTIFIED", "ALREADY_NOTIFIED")]
    assert accepted_titles == ["Old job", "New job"]
