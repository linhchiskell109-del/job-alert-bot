from state import job_hash, is_new, mark_seen


def test_hash_stable_across_url_change():
    job_v1 = {"company": "MoMo", "title": "Associate Product Manager", "location": "Ho Chi Minh", "url": "https://momo.vn/tuyen-dung/apm-123"}
    job_v2 = {"company": "MoMo", "title": "Associate Product Manager", "location": "Ho Chi Minh", "url": "https://momo.vn/tuyen-dung/apm-123?utm=abc&session=xyz"}
    assert job_hash(job_v1) == job_hash(job_v2)


def test_hash_ignores_diacritics_and_case():
    job_v1 = {"company": "MoMo", "title": "Chuyên viên Product", "location": "Hồ Chí Minh", "url": "u1"}
    job_v2 = {"company": "momo", "title": "chuyen vien product", "location": "ho chi minh", "url": "u2"}
    assert job_hash(job_v1) == job_hash(job_v2)


def test_different_title_gives_different_hash():
    job_v1 = {"company": "MoMo", "title": "Associate Product Manager", "location": "HCM", "url": "u1"}
    job_v2 = {"company": "MoMo", "title": "Senior Product Manager", "location": "HCM", "url": "u1"}
    assert job_hash(job_v1) != job_hash(job_v2)


def test_is_new_and_mark_seen_roundtrip():
    state = {"seen": {}}
    job = {"company": "VNG", "title": "Growth Analyst", "location": "Hanoi", "url": "u1"}
    assert is_new(state, job) is True
    mark_seen(state, job)
    assert is_new(state, job) is False
