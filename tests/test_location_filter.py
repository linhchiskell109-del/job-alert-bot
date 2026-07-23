from pipeline import _location_allowed

ALLOWED = ("vietnam", "hanoi", "ho chi minh", "hcmc", "saigon", "sea", "remote vietnam", "hybrid vietnam")


def test_keeps_vietnam_locations():
    assert _location_allowed({"title": "Business Analyst", "location": "Ho Chi Minh City"}, ALLOWED)
    assert _location_allowed({"title": "Business Analyst", "location": "Hanoi"}, ALLOWED)
    assert _location_allowed({"title": "Business Analyst", "location": "Saigon"}, ALLOWED)


def test_keeps_remote_and_hybrid_vietnam():
    assert _location_allowed({"title": "Product Manager", "location": "Remote Vietnam"}, ALLOWED)
    assert _location_allowed({"title": "Product Manager", "location": "Hybrid Vietnam"}, ALLOWED)


def test_rejects_clearly_foreign_location():
    assert not _location_allowed({"title": "Business Analyst", "location": "Singapore"}, ALLOWED)
    assert not _location_allowed({"title": "Business Analyst", "location": "Boston"}, ALLOWED)
    assert not _location_allowed({"title": "Analyst", "location": "Kuala Lumpur, MY"}, ALLOWED)


def test_keeps_unknown_or_missing_location_not_obviously_foreign():
    # Không đủ căn cứ để nói "rõ ràng ở nước khác" -> KHÔNG loại (đúng yêu cầu 1)
    assert _location_allowed({"title": "Business Analyst", "location": "Unknown"}, ALLOWED)
    assert _location_allowed({"title": "Business Analyst", "location": ""}, ALLOWED)


def test_empty_allowed_list_disables_filtering():
    assert _location_allowed({"title": "Business Analyst", "location": "Singapore"}, ())


def test_regional_label_in_title_does_not_override_actual_foreign_location():
    # Bug thực tế: Deloitte gắn nhãn phạm vi "- SEA" vào TITLE cho các role
    # tuyển dụng chung khu vực, dù nơi làm việc thật là Jakarta/Kuala Lumpur —
    # không liên quan gì Việt Nam. Chỉ field location/country mới được tin,
    # KHÔNG được xét title.
    job = {"title": "T&T Consultant - AMS (Success Factors - RCM/RMK/LMS) - SEA",
           "location": "Jakarta, ID"}
    assert not _location_allowed(job, ALLOWED)

    job2 = {"title": "T&T Consultant - Oracle Procurement - SEA",
            "location": "Kuala Lumpur, MY +5 more…"}
    assert not _location_allowed(job2, ALLOWED)


def test_unknown_location_with_explicit_foreign_country_in_title_is_denied():
    # Bug thực tế: Coca-Cola job không trích được location (Unknown) nhưng
    # title nêu rõ tên nước khác (Indonesia/Brazil) — dùng title để LOẠI (an
    # toàn, KHÁC với dùng title để CHO QUA như case "SEA" ở trên).
    job = {"title": "Plant General Manager – Indonesia", "location": "Unknown"}
    assert not _location_allowed(job, ALLOWED)

    job2 = {"title": "Senior Manager, ARTD Marketing - Brazil", "location": "Unknown"}
    assert not _location_allowed(job2, ALLOWED)


def test_unknown_location_without_foreign_marker_still_kept():
    job = {"title": "Merchant Operations Lead", "location": "Unknown"}
    assert _location_allowed(job, ALLOWED)
