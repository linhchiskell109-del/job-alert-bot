"""Load toàn bộ dữ liệu taxonomy (ngành / function / level) + tham số scoring +
company overrides từ các file YAML trong thư mục config/ — KHÔNG có khái niệm
ngành/function/level nào được hard-code trong .py.

Đây là điểm DUY NHẤT trong code đọc các file cấu hình này. Mọi module khác
(matching/engine.py, matching/report.py) chỉ dùng object trả về từ đây.
"""
import os
from dataclasses import dataclass, field

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "config")

TAXONOMY_PATH = os.path.join(CONFIG_DIR, "taxonomy.yaml")
SCORING_PATH = os.path.join(CONFIG_DIR, "scoring.yaml")
OVERRIDES_PATH = os.path.join(CONFIG_DIR, "company_industry_overrides.yaml")


@dataclass
class FunctionDef:
    id: str
    display_name: str
    synonyms: list = field(default_factory=list)
    excluded: bool = False


@dataclass
class LevelDef:
    id: str
    display_name: str
    synonyms: list = field(default_factory=list)
    weight: float = 0.5
    eligible: bool = True


@dataclass
class IndustryDef:
    id: str
    display_name: str
    keywords: list = field(default_factory=list)
    relevant_functions: list = field(default_factory=list)


@dataclass
class Taxonomy:
    industries: dict  # id -> IndustryDef
    functions: dict   # id -> FunctionDef
    levels: dict       # id -> LevelDef


@dataclass
class ScoringConfig:
    weights: dict
    accept_threshold: float
    partial_industry_alignment_ratio: float
    unknown_level_ratio: float
    no_location_filter_ratio: float
    rejection_reason_priority: list


def _read_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_taxonomy(path: str = TAXONOMY_PATH) -> Taxonomy:
    raw = _read_yaml(path)

    industries = {
        industry_id: IndustryDef(
            id=industry_id,
            display_name=data.get("display_name", industry_id),
            keywords=data.get("keywords", []) or [],
            relevant_functions=data.get("relevant_functions", []) or [],
        )
        for industry_id, data in (raw.get("industries") or {}).items()
    }

    functions = {
        function_id: FunctionDef(
            id=function_id,
            display_name=data.get("display_name", function_id),
            synonyms=data.get("synonyms", []) or [],
            excluded=bool(data.get("excluded", False)),
        )
        for function_id, data in (raw.get("functions") or {}).items()
    }

    levels = {
        level_id: LevelDef(
            id=level_id,
            display_name=data.get("display_name", level_id),
            synonyms=data.get("synonyms", []) or [],
            weight=float(data.get("weight", 0.5)),
            eligible=bool(data.get("eligible", True)),
        )
        for level_id, data in (raw.get("levels") or {}).items()
    }

    return Taxonomy(industries=industries, functions=functions, levels=levels)


def load_scoring(path: str = SCORING_PATH) -> ScoringConfig:
    raw = _read_yaml(path)
    weights = raw.get("weights") or {
        "function_match": 45,
        "industry_alignment": 20,
        "level_match": 25,
        "location_match": 10,
    }
    return ScoringConfig(
        weights=weights,
        accept_threshold=float(raw.get("accept_threshold", 60)),
        partial_industry_alignment_ratio=float(raw.get("partial_industry_alignment_ratio", 0.4)),
        unknown_level_ratio=float(raw.get("unknown_level_ratio", 0.5)),
        no_location_filter_ratio=float(raw.get("no_location_filter_ratio", 1.0)),
        rejection_reason_priority=raw.get("rejection_reason_priority") or [
            "excluded_function", "location", "experience", "keyword", "score_too_low",
        ],
    )


def load_company_overrides(path: str = OVERRIDES_PATH) -> dict:
    raw = _read_yaml(path)
    return raw.get("overrides") or {}
