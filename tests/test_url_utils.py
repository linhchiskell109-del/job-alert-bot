from url_utils import normalize_url


def test_strips_utm_params():
    url = "https://example.com/jobs/apm-123?utm_source=linkedin&utm_medium=social"
    assert normalize_url(url) == "https://example.com/jobs/apm-123"


def test_strips_fbclid_and_gclid():
    assert normalize_url("https://example.com/careers?fbclid=abc123") == "https://example.com/careers"
    assert normalize_url("https://example.com/careers?gclid=xyz789") == "https://example.com/careers"


def test_strips_srsltid():
    url = "https://example.com/jobs?srsltid=AfmBOoo123"
    assert normalize_url(url) == "https://example.com/jobs"


def test_keeps_functional_query_params():
    # ?locale=vi_VN không phải tracking param -> phải giữ nguyên
    url = "https://careers.masanconsumer.com/?locale=vi_VN"
    assert normalize_url(url) == "https://careers.masanconsumer.com/?locale=vi_VN"


def test_keeps_id_param_while_stripping_tracking():
    url = "https://example.com/jobs?id=123&utm_campaign=summer"
    assert normalize_url(url) == "https://example.com/jobs?id=123"


def test_strips_fragment():
    url = "https://example.com/careers#job-list"
    assert normalize_url(url) == "https://example.com/careers"


def test_idempotent():
    url = "https://example.com/jobs/apm-123?utm_source=linkedin"
    once = normalize_url(url)
    twice = normalize_url(once)
    assert once == twice


def test_empty_url_returns_empty():
    assert normalize_url("") == ""
