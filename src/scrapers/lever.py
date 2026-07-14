"""Adapter cho ATS Lever — public JSON API, không cần key.
params (tự động phát hiện bởi ats_detector.py): {"company_slug": str}
"""
from http_client import get
from scrapers.base import make_job


def fetch(company: str, params: dict) -> list[dict]:
    slug = params["company_slug"]
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = get(url).json()

    jobs = []
    for j in data:
        categories = j.get("categories") or {}
        location = categories.get("location", "") or ""
        department = categories.get("team", "") or categories.get("department", "") or ""

        jobs.append(make_job(
            company=company,
            title=j.get("text", ""),
            url=j.get("hostedUrl", ""),
            location=location,
            department=department,
            description=j.get("descriptionPlain", "") or "",
        ))
    return jobs
