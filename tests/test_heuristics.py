from heuristics import extract_jobs_from_html

MOMO_LIKE_HTML = """
<html><body>
<div class="job-list">
  <a href="/tuyen-dung/associate-product-manager-1234" class="job-card">
    <h3>Associate Product Manager</h3>
    <span class="location">Hồ Chí Minh</span>
  </a>
  <a href="/tuyen-dung/senior-backend-engineer-5678" class="job-card">
    <h3>Senior Backend Engineer</h3>
    <span class="location">Hà Nội</span>
  </a>
  <a href="/tuyen-dung">Xem tất cả</a>
  <a href="/ve-chung-toi">Về chúng tôi</a>
</div>
</body></html>
"""

QUERY_STRING_HTML = """
<html><body>
<div>
  <a href="/jobs?id=999&title=growth-analyst">
    <div class="title">Growth Analyst</div>
    <div class="job-location">Ho Chi Minh City</div>
  </a>
</div>
</body></html>
"""

GENERIC_TEXT_HTML = """
<html><body>
<div class="card">
  <h4>Business Development Executive</h4>
  <a href="/careers/business-development-executive-001">Apply now</a>
  <span class="dia-diem">Hanoi</span>
</div>
</body></html>
"""


def test_extracts_vietnamese_path_jobs():
    jobs = extract_jobs_from_html(MOMO_LIKE_HTML, "https://momo.vn", "MoMo")
    titles = {j["title"] for j in jobs}
    assert "Associate Product Manager" in titles
    assert "Senior Backend Engineer" in titles
    assert len(jobs) == 2  # "Xem tất cả" (listing link) và "Về chúng tôi" phải bị loại


def test_extracts_location_near_link():
    jobs = extract_jobs_from_html(MOMO_LIKE_HTML, "https://momo.vn", "MoMo")
    by_title = {j["title"]: j for j in jobs}
    assert by_title["Associate Product Manager"]["location"] == "Hồ Chí Minh"
    assert by_title["Senior Backend Engineer"]["location"] == "Hà Nội"


def test_query_string_based_job_link():
    jobs = extract_jobs_from_html(QUERY_STRING_HTML, "https://example.com", "TestCo")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Growth Analyst"
    assert jobs[0]["location"] == "Ho Chi Minh City"


def test_falls_back_to_heading_when_anchor_text_is_generic():
    jobs = extract_jobs_from_html(GENERIC_TEXT_HTML, "https://example.com", "TestCo")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Business Development Executive"


def test_urls_are_absolute():
    jobs = extract_jobs_from_html(MOMO_LIKE_HTML, "https://momo.vn", "MoMo")
    for j in jobs:
        assert j["url"].startswith("https://momo.vn/")


def test_empty_html_returns_empty_list():
    assert extract_jobs_from_html("", "https://example.com", "TestCo") == []


def test_extra_keywords_widen_detection():
    html = """<a href="/co-hoi/data-scientist-42">Data Scientist</a>"""
    assert extract_jobs_from_html(html, "https://example.com", "TestCo") == []
    jobs = extract_jobs_from_html(html, "https://example.com", "TestCo", extra_keywords=("co-hoi",))
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Scientist"
