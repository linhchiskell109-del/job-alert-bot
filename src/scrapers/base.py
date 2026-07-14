"""Kiểu dữ liệu job dùng chung. Các adapter trả về list[dict] cùng format này
(không dùng dataclass instance trực tiếp để dễ serialize/JSON)."""

JOB_FIELDS = ("company", "title", "url", "location", "department", "description")


def make_job(company: str, title: str, url: str, location: str = "",
             department: str = "", description: str = "") -> dict:
    return {
        "company": company,
        "title": title,
        "url": url,
        "location": location,
        "department": department,
        "description": description,
    }
