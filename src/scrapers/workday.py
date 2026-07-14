"""Adapter cho ATS Workday — dùng API JSON công khai (không cần login):
POST https://{tenant}.{wd_number}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

params (tự động phát hiện bởi ats_detector.py): {"tenant", "wd_number", "site"}
"""
from http_client import post
from scrapers.base import make_job


def fetch(company: str, params: dict) -> list[dict]:
    tenant = params["tenant"]
    site = params["site"]
    wd_number = params.get("wd_number", "wd1")

    base = f"https://{tenant}.{wd_number}.myworkdayjobs.com"
    api_url = f"{base}/wday/cxs/{tenant}/{site}/jobs"

    jobs = []
    offset = 0
    limit = 20

    while True:
        payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
        data = post(api_url, json=payload).json()

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for p in postings:
            path = p.get("externalPath", "")
            bullet_fields = p.get("bulletFields") or []
            location = p.get("locationsText") or (bullet_fields[0] if bullet_fields else "")

            jobs.append(make_job(
                company=company,
                title=p.get("title", ""),
                url=f"{base}/{site}{path}",
                location=location,
                department="",
                description="",
            ))

        offset += limit
        if offset >= data.get("total", 0):
            break

    return jobs
