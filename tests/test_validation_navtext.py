from validation import validate_job


def test_rejects_screen_reader_hint_text_as_title():
    result = validate_job({"title": "Opens in a new tab.", "url": "https://x.com/j/1", "location": "Hanoi"})
    assert not result.is_valid


def test_rejects_search_and_apply_cta_as_title():
    result = validate_job({"title": "Search & Apply", "url": "https://x.com/j/1", "location": "Hanoi"})
    assert not result.is_valid
