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
