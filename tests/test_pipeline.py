from pipeline import classify_job_brand

BRANDS = [
    {"company": "ZaloPay", "match_keywords": ["zalopay", "zalo pay", "ví zalopay"]},
    {"company": "VNG", "default": True},
]


def test_classifies_zalopay_job_by_title():
    job = {"title": "Senior Product Manager - ZaloPay", "department": "", "description": ""}
    assert classify_job_brand(job, BRANDS) == "ZaloPay"


def test_classifies_zalopay_job_case_and_diacritic_insensitive():
    job = {"title": "Chuyên viên Ví ZaloPay", "department": "", "description": ""}
    assert classify_job_brand(job, BRANDS) == "ZaloPay"


def test_classifies_zalopay_job_by_department():
    job = {"title": "Business Analyst", "department": "Zalo Pay - Payment", "description": ""}
    assert classify_job_brand(job, BRANDS) == "ZaloPay"


def test_falls_back_to_default_brand():
    job = {"title": "Backend Engineer", "department": "VNG Games", "description": ""}
    assert classify_job_brand(job, BRANDS) == "VNG"


def test_falls_back_to_default_when_no_keywords_match_at_all():
    job = {"title": "Random Job Title", "department": "", "description": ""}
    assert classify_job_brand(job, BRANDS) == "VNG"
