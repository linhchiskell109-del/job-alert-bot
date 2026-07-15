from normalize import normalize_job


def test_splits_concatenated_location_employment_and_title():
    job = {"title": "Hồ Chí MinhFulltimeSenior Manager Product Marketing",
           "url": "https://x.com/j/1", "location": "", "department": ""}
    result = normalize_job(job)
    assert result["title"] == "Senior Manager Product Marketing"
    assert result["location"] == "Ho Chi Minh City"
    assert result["employment_type"] == "Full-time"


def test_reversed_order_employment_then_location_also_splits():
    job = {"title": "FulltimeHanoiBusiness Analyst", "url": "https://x.com/j/2"}
    result = normalize_job(job)
    assert result["employment_type"] == "Full-time"
    assert result["location"] == "Hanoi"
    assert result["title"] == "Business Analyst"


def test_leaves_already_clean_title_untouched():
    job = {"title": "Business Analyst", "url": "https://x.com/j/3", "location": "Hanoi"}
    result = normalize_job(job)
    assert result["title"] == "Business Analyst"
    assert result["location"] == "Hanoi"


def test_canonicalizes_location_field_variants():
    job = {"title": "Business Analyst", "url": "https://x.com/j/4", "location": "HCMC"}
    result = normalize_job(job)
    assert result["location"] == "Ho Chi Minh City"


def test_does_not_overwrite_existing_employment_type():
    job = {"title": "Hồ Chí MinhFulltimeSenior Manager", "url": "https://x.com/j/5",
           "employment_type": "Contract"}
    result = normalize_job(job)
    assert result["employment_type"] == "Contract"
