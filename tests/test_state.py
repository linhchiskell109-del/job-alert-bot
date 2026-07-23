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


def test_unknown_location_does_not_collapse_different_jobs():
    # Audit bug thực tế: khi location="Unknown" (không trích được), 2 job KHÁC
    # NHAU (URL khác) cùng company+title từng bị coi là 1 job — job thứ 2 bị
    # nuốt mất, không bao giờ được báo.
    job_a = {"company": "Coca-Cola", "title": "Warehouse Coordinator",
             "location": "Unknown", "url": "https://x.com/job/111111"}
    job_b = {"company": "Coca-Cola", "title": "Warehouse Coordinator",
             "location": "Unknown", "url": "https://x.com/job/222222"}
    assert job_hash(job_a) != job_hash(job_b)


def test_unknown_location_hash_still_stable_across_query_param_churn():
    job_v1 = {"company": "Coca-Cola", "title": "Warehouse Coordinator",
              "location": "Unknown", "url": "https://x.com/job/111111"}
    job_v2 = {"company": "Coca-Cola", "title": "Warehouse Coordinator",
              "location": "Unknown", "url": "https://x.com/job/111111?utm=abc"}
    assert job_hash(job_v1) == job_hash(job_v2)


def test_known_location_hash_unaffected_by_unknown_location_fix():
    # Job có location trích được bình thường -> hash KHÔNG đổi so với trước
    # (không ảnh hưởng job đã có sẵn trong state.json cũ).
    job_v1 = {"company": "MoMo", "title": "Associate Product Manager", "location": "Ho Chi Minh", "url": "https://momo.vn/apm-123"}
    job_v2 = {"company": "MoMo", "title": "Associate Product Manager", "location": "Ho Chi Minh", "url": "https://momo.vn/apm-123?utm=xyz"}
    assert job_hash(job_v1) == job_hash(job_v2)
