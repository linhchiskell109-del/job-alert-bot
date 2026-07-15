from scrapers.strict_html import _has_job_id


def test_accepts_url_with_long_numeric_id():
    assert _has_job_id("https://careers.bcg.com/global/en/job/12345678") is True


def test_accepts_url_with_uuid():
    assert _has_job_id("https://x.com/job/550e8400-e29b-41d4-a716-446655440000") is True


def test_rejects_nav_link_without_any_id():
    assert _has_job_id("https://careers.bcg.com/global/en/work-at-bcg/faqs") is False
    assert _has_job_id("https://x.com/careers/explore") is False


def test_rejects_short_numbers_that_are_not_real_ids():
    # số ngắn (vd năm '2026') không đủ để coi là job ID thật
    assert _has_job_id("https://x.com/careers/2026-events") is False
