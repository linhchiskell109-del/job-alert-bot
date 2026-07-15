from validation import validate_job

NAV_TITLES = [
    "Work with Us", "Students", "Hiring Process", "Explore", "Learn More",
    "Show all jobs", "What you can do here", "Career Areas", "Tìm công việc",
    "Privacy Policy", "Cookie Notice", "Apply Now", "Search Jobs", "Find Jobs",
]


def _job(title, url="https://x.com/job/1", location="Ho Chi Minh"):
    return {"title": title, "url": url, "location": location}


def test_rejects_navigation_and_menu_titles():
    for title in NAV_TITLES:
        result = validate_job(_job(title))
        assert not result.is_valid, f"expected {title!r} to be rejected"


def test_accepts_real_job_titles_even_if_they_share_a_word_with_blocklist():
    for title in ["Benefits Manager", "Trade Marketing Executive", "Career Development Coach"]:
        result = validate_job(_job(title))
        assert result.is_valid, f"expected {title!r} to be accepted, got reason={result.reason}"


def test_rejects_missing_title():
    result = validate_job({"title": "", "url": "https://x.com/j/1", "location": "Hanoi"})
    assert not result.is_valid
    assert result.reason == "missing_field:title"


def test_rejects_missing_url():
    result = validate_job({"title": "Real Job", "url": "", "location": "Hanoi"})
    assert not result.is_valid
    assert result.reason == "missing_field:url"


def test_rejects_missing_location_and_country():
    result = validate_job({"title": "Real Job", "url": "https://x.com/j/1"})
    assert not result.is_valid
    assert result.reason == "missing_any_of:location/country"


def test_accepts_when_country_present_instead_of_location():
    result = validate_job({"title": "Real Job", "url": "https://x.com/j/1", "country": "Vietnam"})
    assert result.is_valid


def test_rejects_title_too_short():
    result = validate_job(_job("QA"))
    assert not result.is_valid
