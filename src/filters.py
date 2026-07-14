"""Filter logic: quyết định 1 job có match tiêu chí (keyword / level / location)."""
import re

from textnorm import normalize


def _contains_any(haystack: str, needles: list[str]) -> bool:
    h = normalize(haystack)
    for n in needles:
        n_norm = normalize(n)
        pattern = r"(?<![a-z0-9])" + re.escape(n_norm) + r"(?![a-z0-9])"
        if re.search(pattern, h):
            return True
    return False


def job_matches(job: dict, config: dict) -> bool:
    keywords = config.get("jd_keywords", [])
    levels = config.get("levels", [])
    locations = config.get("locations", [])
    match_mode = config.get("match_mode", "AND")

    title = job.get("title", "")
    description = job.get("description", "") or ""
    location = job.get("location", "")

    title_and_desc = f"{title} {description}"

    keyword_ok = _contains_any(title_and_desc, keywords) if keywords else True
    if match_mode == "keyword_only":
        return keyword_ok

    level_ok = _contains_any(title_and_desc, levels) if levels else True
    location_ok = _contains_any(f"{title} {location}", locations) if locations else True

    return keyword_ok and level_ok and location_ok
