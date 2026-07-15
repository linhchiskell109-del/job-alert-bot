"""Semantic career matching engine.

Thay thế keyword filter nhị phân (PASS/FAIL) cũ (src/filters.py) bằng 1 pipeline
4 bước, dữ liệu 100% lấy từ config/taxonomy.yaml + config/scoring.yaml +
config/company_industry_overrides.yaml (xem matching/taxonomy.py) — file .py
này KHÔNG chứa bất kỳ tên ngành/function/level/synonym nào, chỉ chứa THUẬT TOÁN
so khớp + tính điểm áp dụng chung cho mọi ngành.

  1. detect_industry()  — công ty này thuộc ngành nào (override thủ công trước,
                           không có thì suy ra từ keyword trong title/JD).
  2. detect_function()  — title/JD khớp function chuẩn hoá nào (Product/Growth/
                           Marketing/Trade Marketing/...).
  3. detect_level()      — title/JD khớp level chuẩn hoá nào (entry/mid/senior).
  4. score()              — cộng điểm có trọng số (function/industry/level/
                           location) -> ACCEPT nếu >= accept_threshold VÀ không
                           dính lý do loại "cứng" (excluded function / location
                           bắt buộc không khớp).

So khớp KHÔNG chỉ dựa vào exact keyword nữa (xem `_match_confidence`) — có 3
tầng, từ cụ thể nhất đến "gợi ý":
  a. Exact phrase (word-boundary substring)         -> confidence 1.0
  b. Token overlap (đủ >=60% số từ của synonym xuất
     hiện đâu đó trong title/JD, không cần liền
     nhau/đúng thứ tự — vd "Merchant Strategy Lead"
     vẫn khớp synonym "merchant strategy")            -> confidence 0.75 * tỉ lệ
  c. Fuzzy single-word (đồng nghĩa 1 từ, gần đúng
     chính tả/biến thể, vd "Consultants" ~ "consultant") -> confidence 0.6

Synonym khớp CONFIDENCE cao nhất thắng; nếu bằng nhau, synonym dài/cụ thể hơn
thắng. Việc này giúp engine nhận ra job dùng cách diễn đạt khác thay vì đòi hỏi
khớp nguyên văn cụm từ trong taxonomy.yaml — đúng tinh thần "semantic" thay vì
"exact keyword".

Mọi job (accept hay reject) đều trả về 1 MatchResult đầy đủ để phục vụ
explainability logging (matching/report.py) — không có nhánh nào trả về chỉ
True/False như filters.py cũ.
"""
import difflib
import re
from dataclasses import dataclass, field

from matching.taxonomy import ScoringConfig, Taxonomy
from textnorm import normalize

# Dưới ngưỡng này, 1 match được coi là "quá yếu để tin cậy" — không dùng để hard
# reject (excluded_function / experience), chỉ dùng cho scoring tham khảo.
HARD_FAIL_CONFIDENCE_THRESHOLD = 0.75

# Token overlap: cần >= tỉ lệ này số từ của synonym xuất hiện trong haystack.
TOKEN_OVERLAP_MIN_RATIO = 0.6
TOKEN_OVERLAP_BASE_CONFIDENCE = 0.75

# Fuzzy single-word: yêu cầu SequenceMatcher ratio >= ngưỡng này để tính là "gần
# đúng" (chấp nhận sai chính tả nhẹ / biến thể số nhiều, KHÔNG chấp nhận từ khác
# nghĩa tình cờ giống mặt chữ).
FUZZY_WORD_MIN_SIMILARITY = 0.84
FUZZY_WORD_CONFIDENCE = 0.6
FUZZY_WORD_MIN_LEN = 4  # bỏ qua từ quá ngắn (dễ match nhầm, ít thông tin)


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


def _tokenize(text_norm: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text_norm))


def _contains(haystack_norm: str, needle: str) -> bool:
    """Exact phrase match, word-boundary — dùng cho industry keywords/location
    (những trường hợp cần chính xác, không cần fuzzy)."""
    needle_norm = normalize(needle)
    if not needle_norm:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle_norm) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _match_confidence(haystack_norm: str, haystack_tokens: set, synonym: str) -> float:
    """Trả về độ tin cậy (0.0 - 1.0) rằng `synonym` mô tả đúng nội dung trong
    haystack — KHÔNG đòi hỏi khớp nguyên văn cụm từ. Xem 3 tầng ở docstring đầu
    file."""
    syn_norm = normalize(synonym)
    if not syn_norm:
        return 0.0

    # a. Exact phrase (word-boundary) — cụ thể nhất, tin cậy tuyệt đối.
    if _contains(haystack_norm, synonym):
        return 1.0

    syn_tokens = [t for t in re.findall(r"[a-z0-9]+", syn_norm) if t]
    if not syn_tokens:
        return 0.0

    # b. Token overlap cho synonym nhiều từ — không cần liền nhau/đúng thứ tự.
    if len(syn_tokens) > 1:
        matched = sum(1 for t in syn_tokens if t in haystack_tokens)
        ratio = matched / len(syn_tokens)
        if ratio >= TOKEN_OVERLAP_MIN_RATIO:
            return TOKEN_OVERLAP_BASE_CONFIDENCE * ratio

    # c. Fuzzy single-word — chấp nhận biến thể gần đúng (số nhiều, hậu tố...).
    else:
        word = syn_tokens[0]
        if len(word) >= FUZZY_WORD_MIN_LEN:
            for tok in haystack_tokens:
                if len(tok) < FUZZY_WORD_MIN_LEN:
                    continue
                similarity = difflib.SequenceMatcher(None, tok, word).ratio()
                if similarity >= FUZZY_WORD_MIN_SIMILARITY:
                    return FUZZY_WORD_CONFIDENCE

    return 0.0


def _best_synonym_match(haystack_norm: str, haystack_tokens: set, synonym_map: dict) -> tuple:
    """synonym_map: {id -> list[synonym]}. Trả về (id, matched_synonym, confidence)
    có confidence CAO NHẤT; hoà thì synonym DÀI HƠN (cụ thể hơn) thắng. Trả về
    (None, None, 0.0) nếu không khớp gì (kể cả fuzzy)."""
    best_id, best_syn, best_conf, best_len = None, None, 0.0, -1
    for item_id, synonyms in synonym_map.items():
        for syn in synonyms:
            conf = _match_confidence(haystack_norm, haystack_tokens, syn)
            if conf <= 0:
                continue
            if (conf, len(syn)) > (best_conf, best_len):
                best_id, best_syn, best_conf, best_len = item_id, syn, conf, len(syn)
    return best_id, best_syn, best_conf


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


def detect_function(text_norm: str, text_tokens: set, taxonomy: Taxonomy) -> tuple:
    synonym_map = {fid: f.synonyms for fid, f in taxonomy.functions.items()}
    return _best_synonym_match(text_norm, text_tokens, synonym_map)


def detect_level(text_norm: str, text_tokens: set, taxonomy: Taxonomy) -> tuple:
    synonym_map = {lid: l.synonyms for lid, l in taxonomy.levels.items()}
    return _best_synonym_match(text_norm, text_tokens, synonym_map)


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
    text_tokens = _tokenize(text_norm)

    industry_id = detect_industry(company_name, text_norm, taxonomy, company_overrides)
    industry = taxonomy.industries.get(industry_id)

    function_id, _, function_conf = detect_function(text_norm, text_tokens, taxonomy)
    function = taxonomy.functions.get(function_id) if function_id else None

    level_id, _, level_conf = detect_level(text_norm, text_tokens, taxonomy)
    level = taxonomy.levels.get(level_id) if level_id else None

    location_ok = _location_ok(job, locations)

    reasons = []  # danh sách các lý do loại "ứng viên" — chọn theo priority ở cuối

    # --- Hard fail: function bị loại hẳn (Engineering/HR/Legal/Finance thuần) ---
    # Chỉ hard-reject khi confidence đủ cao — match fuzzy/token-overlap yếu
    # không nên tự loại thẳng 1 job có thể vẫn liên quan.
    if function is not None and function.excluded and function_conf >= HARD_FAIL_CONFIDENCE_THRESHOLD:
        reasons.append("excluded_function")

    # --- Location bắt buộc nhưng không khớp ---
    if not location_ok:
        reasons.append("location")

    # --- Level quá cao (không eligible) so với target entry-level ---
    if level is not None and not level.eligible and level_conf >= HARD_FAIL_CONFIDENCE_THRESHOLD:
        reasons.append("experience")

    # --- Không tìm thấy function nào liên quan (kể cả fuzzy) trong title/JD ---
    if function is None:
        reasons.append("keyword")

    # ---- Scoring (vẫn tính dù có hard-fail, để log điểm tham khảo) ----
    w = scoring.weights
    is_excluded_match = function is not None and function.excluded and function_conf >= HARD_FAIL_CONFIDENCE_THRESHOLD
    function_score = function_conf if (function is not None and not is_excluded_match) else 0.0

    if function is not None and not is_excluded_match and industry is not None:
        if function.id in industry.relevant_functions:
            alignment_score = 1.0
        else:
            alignment_score = scoring.partial_industry_alignment_ratio
    else:
        alignment_score = 0.0

    if level is None:
        level_score = scoring.unknown_level_ratio
    else:
        level_score = level.weight * max(level_conf, 0.5)  # confidence thấp -> giảm điểm nhưng không về 0

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
        match_kind = "khớp chính xác" if function_conf >= 0.999 else f"khớp gần đúng ({function_conf:.0%})"
        reason, detail = "accepted", (
            f"{function.display_name} / {industry.display_name} / "
            f"{level.display_name if level else 'level không rõ'} — score {total} ({match_kind})"
        )
    else:
        reason = next((r for r in scoring.rejection_reason_priority if r in reasons), reasons[0])
        detail_map = {
            "excluded_function": f"function '{function.display_name}' không liên quan (loại hẳn)" if function else "",
            "location": "địa điểm không khớp danh sách locations trong config.yaml",
            "experience": f"level '{level.display_name}' cao hơn entry-level mục tiêu" if level else "",
            "keyword": "không tìm thấy function nào liên quan (kể cả gần đúng) trong title/JD",
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
