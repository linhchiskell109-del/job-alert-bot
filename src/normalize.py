"""Normalize layer — bước ĐẦU TIÊN trong pipeline, ngay sau Scraper:

    Scraper -> Normalize -> Validate -> Matching -> Notification

Nhiều scraper (đặc biệt html_scraper/playwright_scraper dùng heuristic chung)
gom text của cả job card thành 1 chuỗi dính liền, vd:

    "Hồ Chí MinhFulltimeSenior Manager Product Marketing"

thay vì tách sẵn location/employment_type/title. Module này tách chuỗi đó
thành field riêng biệt:

    Title: "Senior Manager, Product Marketing"
    Location: "Ho Chi Minh City"
    Employment: "Full-time"

Thuật toán (áp dụng chung, không phân biệt công ty nào):
  1. "Camel-split" — chèn khoảng trắng vào mọi điểm chữ thường theo ngay sau
     bởi chữ hoa (dấu hiệu ranh giới 2 "từ" bị dính liền do scraper heuristic
     gom text, KHÔNG phải do chính job title viết hoa giữa câu — tên chức danh
     thật hiếm khi có kiểu viết hoa giữa từ như vậy).
  2. Từ ĐẦU chuỗi đã tách, thử "nuốt" (consume) 1 địa danh biết trước
     (config/normalize.yaml -> known_locations) làm prefix — thử cụm dài nhất
     trước (vd "Hồ Chí Minh" 3 từ) rồi mới đến ngắn hơn.
  3. Tiếp tục thử "nuốt" 1 employment_type biết trước làm prefix kế tiếp.
  4. Lặp lại bước 2-3 (thứ tự location/employment_type trong text nguồn có thể
     đảo ngược) cho đến khi không nuốt được gì nữa — phần còn lại là title thật.

Nếu job đã có sẵn `location`/`employment_type` tách riêng (từ ATS adapter có
structured data), module này GIỮ NGUYÊN, chỉ dùng để làm sạch thêm (canonicalize
tên địa danh) chứ không ghi đè dữ liệu đã đúng.
"""
import os
from dataclasses import dataclass

import yaml

from textnorm import normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "normalize.yaml")

_CACHE = None

MAX_PREFIX_WINDOW = 4  # tối đa 4 "từ" cho 1 cụm địa danh/employment_type


@dataclass
class NormalizeConfig:
    employment_types: dict  # canonical -> list[synonym]
    known_locations: dict   # canonical -> list[synonym]


def load_normalize_config(path: str = CONFIG_PATH, force_reload: bool = False) -> NormalizeConfig:
    global _CACHE
    if _CACHE is None or force_reload:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _CACHE = NormalizeConfig(
            employment_types=raw.get("employment_types", {}) or {},
            known_locations=raw.get("known_locations", {}) or {},
        )
    return _CACHE


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _camel_split(text: str) -> str:
    """Chèn khoảng trắng ở mọi ranh giới chữ_thường -> Chữ_hoa (dấu hiệu 2 cụm
    bị dính liền do scraper gom text, vd 'MinhFulltime' -> 'Minh Fulltime').
    Dùng str.islower()/isupper() (unicode-aware, hoạt động đúng với tiếng Việt
    có dấu) thay vì regex character-class để tránh vấn đề unicode ranges."""
    if not text:
        return text
    out = [text[0]]
    for i in range(1, len(text)):
        prev, cur = text[i - 1], text[i]
        if prev.islower() and cur.isupper():
            out.append(" ")
        out.append(cur)
    return "".join(out)


def _flat_synonym_map(canonical_map: dict) -> dict:
    """canonical -> [synonyms] thành synonym_norm -> canonical, để tra cứu O(1)."""
    flat = {}
    for canonical, synonyms in canonical_map.items():
        for syn in synonyms:
            flat[normalize(syn)] = canonical
        flat[normalize(canonical)] = canonical
    return flat


def _consume_prefix(tokens: list, flat_map: dict) -> tuple:
    """Thử khớp `flat_map` với cụm DÀI NHẤT (tối đa MAX_PREFIX_WINDOW từ) ở
    ĐẦU `tokens`. Trả về (canonical, số_từ_đã_nuốt) hoặc (None, 0)."""
    max_window = min(MAX_PREFIX_WINDOW, len(tokens))
    for window in range(max_window, 0, -1):
        candidate = normalize(" ".join(tokens[:window]))
        if candidate in flat_map:
            return flat_map[candidate], window
    return None, 0


def _canonicalize_location_text(text: str, flat_locations: dict) -> str:
    """Nếu TOÀN BỘ `text` (sau chuẩn hoá) khớp thẳng 1 địa danh biết trước, trả
    về canonical form; nếu không, giữ nguyên nguyên văn."""
    text_clean = _clean(text)
    if not text_clean:
        return text_clean
    norm = normalize(text_clean)
    return flat_locations.get(norm, text_clean)


def normalize_job(job: dict, config: NormalizeConfig = None) -> dict:
    config = config or load_normalize_config()
    flat_locations = _flat_synonym_map(config.known_locations)
    flat_employment = _flat_synonym_map(config.employment_types)

    result = dict(job)
    title = _clean(job.get("title", ""))
    location = _clean(job.get("location", ""))
    employment_type = _clean(job.get("employment_type", ""))
    department = _clean(job.get("department", ""))

    # ---- Tách title đã camel-split thành các phần: location? employment_type? title thật ----
    tokens = _camel_split(title).split()
    consumed_location, consumed_employment = None, None

    changed = True
    while changed and tokens:
        changed = False
        if consumed_location is None:
            canon, n = _consume_prefix(tokens, flat_locations)
            if canon:
                consumed_location, tokens, changed = canon, tokens[n:], True
                continue
        if consumed_employment is None:
            canon, n = _consume_prefix(tokens, flat_employment)
            if canon:
                consumed_employment, tokens, changed = canon, tokens[n:], True
                continue

    new_title = " ".join(tokens).strip(" ,-–—")
    if new_title:
        title = new_title

    if consumed_location and not location:
        location = consumed_location
    if consumed_employment and not employment_type:
        employment_type = consumed_employment

    # ---- Canonicalize location field (dù đến từ ATS structured data hay vừa tách) ----
    if location:
        location = _canonicalize_location_text(location, flat_locations)

    result["title"] = title
    result["location"] = location
    result["employment_type"] = employment_type
    result["department"] = department
    return result
