"""Semantic career matching engine.

Thay thế keyword filter nhị phân (PASS/FAIL) cũ (src/filters.py) bằng 1 pipeline
4 bước, dữ liệu 100% lấy từ config/taxonomy.yaml + config/scoring.yaml +
config/company_industry_overrides.yaml (xem matching/taxonomy.py) — file .py
này KHÔNG chứa bất kỳ tên ngành/function/level/synonym nào, chỉ chứa THUẬT TOÁN
so khớp + tính điểm áp dụng chung cho mọi ngành.

  1. detect_industry()  — công ty này thuộc ngành nào (override thủ công trước,
                           không có thì suy ra từ keyword trong title/JD).
  2. detect_function()  — title/JD khớp function chuẩn hoá nào (Product/Growth/
                           Marketing/Trade Marketing/...), match theo synonym
                           dài nhất (cụ thể nhất) để tránh match nhầm quá rộng.
  3. detect_level()      — title/JD khớp level chuẩn hoá nào (entry/mid/senior).
  4. score()              — cộng điểm có trọng số (function/industry/level/
                           location) -> ACCEPT nếu >= accept_threshold VÀ không
                           dính lý do loại "cứng" (excluded function / location
                           bắt buộc không khớp).

Mọi job (accept hay reject) đều trả về 1 MatchResult đầy đủ để phục vụ
explainability logging (matching/report.py) — không có nhánh nào trả về chỉ
True/False như filters.py cũ.
"""
import re
from dataclasses import dataclass, field

from matching.taxonomy import ScoringConfig, Taxonomy
from textnorm import normalize


@dataclass
class MatchResult:
    accepted: bool
    score: float
    industry: str
    industry_display: str
    function: str | None
    function_display: str | None
    level: str | None
    level_display: str | None
    location_ok: bool
    reason: str          # "accepted" | 1 trong rejection_reason_priority
    reason_detail: str    # câu giải thích ngắn, dùng trong log


def _norm(text: str) -> str:
    return normalize(text or "")


def _contains(haystack_norm: str, needle: str) -> bool:
    needle_norm = normalize(needle)
    if not needle_norm:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle_norm) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _best_synonym_match(haystack_norm: str, synonym_map: dict) -> tuple:
    """synonym_map: {id -> list[synonym]}. Trả về (id, matched_synonym) có
    synonym DÀI NHẤT khớp được (ưu tiên cụ thể hơn tổng quát, vd 'business
    analyst' thắng 'analyst'). Trả về (None, None) nếu không khớp gì."""
    best_id, best_syn, best_len = None, None, -1
    for item_id, synonyms in synonym_map.items():
        for syn in synonyms:
            if len(syn) > best_len and _contains(haystack_norm, syn):
                best_id, best_syn, best_len = item_id, syn, len(syn)
    return best_id, best_syn


def detect_industry(company_name: str, text_norm: str, taxonomy: Taxonomy,
                     company_overrides: dict) -> str:
    override = company_overrides.get(company_name)
    if override and override in taxonomy.industries:
        return override

    for industry_id, industry in taxonomy.industries.items():
        if industry_id == "general":
            continue
        for kw in industry.keywords:
            if _contains(text_norm, kw):
                return industry_id

    return "general" if "general" in taxonomy.industries else next(iter(taxonomy.industries), "general")


def detect_function(text_norm: str, taxonomy: Taxonomy) -> tuple:
    synonym_map = {fid: f.synonyms for fid, f in taxonomy.functions.items()}
    return _best_synonym_match(text_norm, synonym_map)


def detect_level(text_norm: str, taxonomy: Taxonomy) -> tuple:
    synonym_map = {lid: l.synonyms for lid, l in taxonomy.levels.items()}
    return _best_synonym_match(text_norm, synonym_map)


def _location_ok(job: dict, locations: list) -> bool:
    if not locations:
        return True
    haystack = _norm(f"{job.get('title', '')} {job.get('location', '')}")
    return any(_contains(haystack, loc) for loc in locations)


def evaluate_job(job: dict, company_cfg: dict, locations: list,
                  taxonomy: Taxonomy, scoring: ScoringConfig,
                  company_overrides: dict) -> MatchResult:
    company_name = company_cfg.get("name") or job.get("company", "")
    title = job.get("title", "")
    description = job.get("description", "") or ""
    text_norm = _norm(f"{title} {description}")

    industry_id = detect_industry(company_name, text_norm, taxonomy, company_overrides)
    industry = taxonomy.industries.get(industry_id)

    function_id, _ = detect_function(text_norm, taxonomy)
    function = taxonomy.functions.get(function_id) if function_id else None

    level_id, _ = detect_level(text_norm, taxonomy)
    level = taxonomy.levels.get(level_id) if level_id else None

    location_ok = _location_ok(job, locations)

    reasons = []  # danh sách các lý do loại "ứng viên" — chọn theo priority ở cuối

    # --- Hard fail: function bị loại hẳn (Engineering/HR/Legal/Finance thuần) ---
    if function is not None and function.excluded:
        reasons.append("excluded_function")

    # --- Location bắt buộc nhưng không khớp ---
    if not location_ok:
        reasons.append("location")

    # --- Level quá cao (không eligible) so với target entry-level ---
    if level is not None and not level.eligible:
        reasons.append("experience")

    # --- Không tìm thấy function nào liên quan trong title/JD ---
    if function is None:
        reasons.append("keyword")

    # ---- Scoring (vẫn tính dù có hard-fail, để log điểm tham khảo) ----
    w = scoring.weights
    function_score = 1.0 if (function is not None and not function.excluded) else 0.0

    if function is not None and not function.excluded and industry is not None:
        if function.id in industry.relevant_functions:
            alignment_score = 1.0
        else:
            alignment_score = scoring.partial_industry_alignment_ratio
    else:
        alignment_score = 0.0

    if level is None:
        level_score = scoring.unknown_level_ratio
    else:
        level_score = level.weight

    location_score = 1.0 if location_ok else 0.0
    if not locations:
        location_score = scoring.no_location_filter_ratio

    total = (
        function_score * w.get("function_match", 0)
        + alignment_score * w.get("industry_alignment", 0)
        + level_score * w.get("level_match", 0)
        + location_score * w.get("location_match", 0)
    )
    total = round(total, 1)

    if not reasons and total < scoring.accept_threshold:
        reasons.append("score_too_low")

    accepted = not reasons

    if accepted:
        reason, detail = "accepted", (
            f"{function.display_name} / {industry.display_name} / "
            f"{level.display_name if level else 'level không rõ'} — score {total}"
        )
    else:
        reason = next((r for r in scoring.rejection_reason_priority if r in reasons), reasons[0])
        detail_map = {
            "excluded_function": f"function '{function.display_name}' không liên quan (loại hẳn)" if function else "",
            "location": "địa điểm không khớp danh sách locations trong config.yaml",
            "experience": f"level '{level.display_name}' cao hơn entry-level mục tiêu" if level else "",
            "keyword": "không tìm thấy function nào liên quan trong title/JD",
            "score_too_low": f"score {total} < accept_threshold {scoring.accept_threshold}",
        }
        detail = detail_map.get(reason, reason)

    return MatchResult(
        accepted=accepted,
        score=total,
        industry=industry_id,
        industry_display=industry.display_name if industry else industry_id,
        function=function.id if function else None,
        function_display=function.display_name if function else None,
        level=level.id if level else None,
        level_display=level.display_name if level else None,
        location_ok=location_ok,
        reason=reason,
        reason_detail=detail,
    )
