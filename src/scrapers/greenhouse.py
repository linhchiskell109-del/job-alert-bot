"""Adapter cho ATS Greenhouse — public JSON API, không cần key.
params (tự động phát hiện bởi ats_detector.py): {"board_token": str}
"""
from http_client import get
from scrapers.base import make_job


def fetch(company: str, params: dict) -> list[dict]:
    board_token = params["board_token"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    data = get(url).json()

    jobs = []
    for j in data.get("jobs", []):
        location = (j.get("location") or {}).get("name", "")
        departments = j.get("departments") or []
        department = ", ".join(d.get("name", "") for d in departments if d.get("name"))

        jobs.append(make_job(
            company=company,
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            location=location,
            department=department,
            description=j.get("content", "") or "",
        ))
    return jobs
