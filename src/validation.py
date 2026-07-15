"""Validation layer — đứng GIỮA Normalize và Matching trong pipeline:

    Scraper -> Normalize -> Validate -> Matching -> Notification

Nhiệm vụ DUY NHẤT: xác định 1 job (đã normalize) có phải là 1 JOB POSTING THẬT
hay chỉ là trang điều hướng/menu (nav page) lọt vào do scraper quá lỏng lẻo
(vd anchor "Explore", "Learn More", "Show all jobs" tình cờ khớp pattern URL
job của heuristic). Dữ liệu blocklist/required-fields 100% ở config/validation.yaml
— file này chỉ chứa thuật toán kiểm tra, không hard-code từ khoá nào.

2 lớp kiểm tra:
  1. required_fields / required_any_of — job THIẾU field bắt buộc (title, url,
     và location HOẶC country) bị loại ngay, không cần xét blocklist.
  2. nav_blocklist — title (sau chuẩn hoá, bỏ dấu, lowercase) TRÙNG NGUYÊN VĂN
     1 cụm trong blocklist, HOẶC sau khi bóc hết các cụm blocklist khớp được ra
     khỏi title mà phần còn lại quá ngắn (không đủ nội dung job thật) -> loại.
     Cách này KHÔNG loại nhầm job có tên chứa 1 từ trong blocklist làm 1 phần
     (vd "Benefits Manager" vẫn hợp lệ vì sau khi bóc "benefits" ra vẫn còn
     "Manager" — đủ dài để coi là nội dung job thật).
"""
import os
import re
from dataclasses import dataclass

import yaml

from textnorm import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "validation.yaml")

_CACHE = None


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str  # "" nếu valid, else "missing_field:<f>" | "missing_any_of:<..>" | "title_too_short" | "nav_blocklist_exact" | "nav_blocklist_content"


def load_validation_config(path: str = CONFIG_PATH, force_reload: bool = False) -> dict:
    global _CACHE
    if _CACHE is None or force_reload:
        with open(path, "r", encoding="utf-8") as f:
            _CACHE = yaml.safe_load(f) or {}
    return _CACHE


def _word_boundary_strip(text_norm: str, phrase_norm: str) -> str:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase_norm) + r"(?![a-z0-9])"
    return re.sub(pattern, " ", text_norm)


def validate_job(job: dict, config: dict = None) -> ValidationResult:
    config = config or load_validation_config()

    required_fields = config.get("required_fields", ["title", "url"])
    required_any_of = config.get("required_any_of", [])
    min_len = config.get("min_title_length", 4)
    blocklist = config.get("nav_blocklist_phrases", [])

    # ---- 1. Required fields ----
    for field_name in required_fields:
        if not str(job.get(field_name, "") or "").strip():
            return ValidationResult(False, f"missing_field:{field_name}")

    for group in required_any_of:
        if not any(str(job.get(f, "") or "").strip() for f in group):
            return ValidationResult(False, f"missing_any_of:{'/'.join(group)}")

    title = str(job.get("title", "") or "").strip()
    if len(title) < min_len:
        return ValidationResult(False, "title_too_short")

    # ---- 2. Nav/menu blocklist ----
    title_norm = normalize(title)
    blocklist_norm = [normalize(p) for p in blocklist if p]

    # Exact match (title CHÍNH LÀ 1 cụm nav, vd title = "Explore" hoặc "Learn More")
    if title_norm in blocklist_norm:
        return ValidationResult(False, "nav_blocklist_exact")

    # Bóc hết các cụm blocklist khớp được (word-boundary) ra khỏi title, nếu
    # phần còn lại quá ngắn thì coi như title chỉ là nav text ghép lại.
    stripped = title_norm
    for phrase_norm in blocklist_norm:
        if phrase_norm and phrase_norm in stripped:
            stripped = _word_boundary_strip(stripped, phrase_norm)
    stripped = re.sub(r"\s+", " ", stripped).strip()

    if len(stripped) < min_len:
        return ValidationResult(False, "nav_blocklist_content")

    return ValidationResult(True, "")
