import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config.setdefault("extra_job_url_keywords", [])
    config.setdefault("jd_keywords", [])
    config.setdefault("levels", [])
    config.setdefault("locations", [])
    config.setdefault("match_mode", "AND")
    return config
