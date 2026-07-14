from filters import job_matches

CONFIG = {
    "jd_keywords": ["product manager", "growth", "business analyst"],
    "levels": ["associate", "fresher", "intern"],
    "locations": ["vn", "vietnam", "hcm", "hanoi"],
    "match_mode": "AND",
}


def test_matches_all_criteria():
    job = {"title": "Associate Product Manager", "location": "Ho Chi Minh City, Vietnam"}
    assert job_matches(job, CONFIG) is True


def test_fails_on_seniority_not_in_levels():
    job = {"title": "Senior Product Manager", "location": "Ho Chi Minh City, Vietnam"}
    assert job_matches(job, CONFIG) is False


def test_fails_on_location():
    job = {"title": "Associate Product Manager", "location": "Singapore"}
    assert job_matches(job, CONFIG) is False


def test_fails_on_keyword():
    job = {"title": "Associate Software Engineer", "location": "Hanoi, Vietnam"}
    assert job_matches(job, CONFIG) is False


def test_keyword_only_mode_ignores_level_and_location():
    config = {**CONFIG, "match_mode": "keyword_only"}
    job = {"title": "Senior Growth Manager", "location": "Singapore"}
    assert job_matches(job, config) is True


def test_word_boundary_prevents_false_positive():
    # "ops" không được match nhầm trong "shops"
    config = {"jd_keywords": ["ops"], "levels": [], "locations": [], "match_mode": "AND"}
    job = {"title": "Shops Category Manager", "location": ""}
    assert job_matches(job, config) is False
