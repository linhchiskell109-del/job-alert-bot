import os

import yaml

from url_utils import normalize_url

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config.setdefault("companies", [])
    config.setdefault("shared_portals", [])
    config.setdefault("extra_job_url_keywords", [])
    config.setdefault("jd_keywords", [])
    config.setdefault("levels", [])
    config.setdefault("locations", [])
    config.setdefault("match_mode", "AND")

    # Chuẩn hoá URL (bỏ tracking param như utm_/fbclid/gclid/srsltid) ngay khi load,
    # để mọi nơi dùng config.yaml sau đó đều thấy URL đã sạch.
    for company in config["companies"]:
        company["url"] = normalize_url(company["url"])

    for portal in config["shared_portals"]:
        portal["url"] = normalize_url(portal["url"])

    return config
