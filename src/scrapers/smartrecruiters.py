"""Adapter cho ATS SmartRecruiters — public API, không cần key:
https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings

params (tự động phát hiện bởi ats_detector.py): {"company_identifier": str}
"""
from http_client import get
from scrapers.base import make_job


def fetch(company: str, params: dict) -> list[dict]:
    identifier = params["company_identifier"]
    base_url = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"

    jobs = []
    offset = 0
    limit = 100

    while True:
        data = get(base_url, params={"limit": limit, "offset": offset}).json()
        postings = data.get("content", [])
        if not postings:
            break

        for p in postings:
            location_obj = p.get("location") or {}
            location = ", ".join(
                filter(None, [location_obj.get("city"), location_obj.get("region"), location_obj.get("country")])
            )
            department = (p.get("department") or {}).get("label", "") or (p.get("function") or {}).get("label", "")
            posting_id = p.get("id", "")
            job_url = f"https://jobs.smartrecruiters.com/{identifier}/{posting_id}"

            jobs.append(make_job(
                company=company,
                title=p.get("name", ""),
                url=job_url,
                location=location,
                department=department,
                description="",
            ))

        offset += limit
        if offset >= data.get("totalFound", 0):
            break

    return jobs
