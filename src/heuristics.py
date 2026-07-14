"""Heuristic tự động nhận diện job listing trong HTML — KHÔNG dùng CSS selector
khai báo thủ công cho từng công ty. Dùng chung cho html_scraper (HTML tĩnh) và
playwright_scraper (HTML đã render JS) — cùng 1 hàm extract_jobs_from_html().

Chiến lược:
1. Quét tất cả <a href> trong trang, giữ lại các href có pattern giống link job
   (chứa 1 trong các từ khoá path: jobs/careers/positions/openings/vacancy/roles,
   và cả các biến thể tiếng Việt: tuyen-dung/viec-lam/vi-tri...).
2. Loại các href chỉ trỏ về đúng trang danh sách (không có id/slug cụ thể).
3. Title = text của thẻ <a>; nếu quá ngắn/rỗng/generic ("Xem chi tiết", "Apply")
   thì tìm heading (h1-h5/strong) gần nhất bên trong hoặc trong card cha.
4. Location = tìm phần tử có class/id chứa "location"/"place"/"city"/"dia-diem"
   trong cùng khối cha với link (đi lên tối đa 4 cấp).
5. Dedupe theo URL tuyệt đối.

Đây là điểm DUY NHẤT trong code cần chỉnh nếu 1 trang có URL pattern quá khác biệt
(vd dùng path tiếng Anh/Việt không có trong danh sách) — sửa 1 lần ở đây áp dụng
cho MỌI công ty, thay vì phải sửa selector riêng cho từng công ty như trước.
Ngoài ra có thể thêm từ khoá riêng qua `extra_job_url_keywords` trong config.yaml
mà không cần sửa code.
"""
import copy
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

DEFAULT_JOB_PATH_KEYWORDS = (
    "job", "jobs", "career", "careers", "position", "positions",
    "opening", "openings", "vacancy", "vacancies", "role", "roles",
    "tuyen-dung", "tuyendung", "viec-lam", "vieclam", "vi-tri", "vitri",
    "co-hoi-nghe-nghiep", "ung-tuyen", "ungtuyen", "recruitment", "hiring",
)

GENERIC_LAST_SEGMENTS = {
    "job", "jobs", "career", "careers", "position", "positions",
    "opening", "openings", "vacancy", "vacancies", "role", "roles", "search",
    "tuyen-dung", "tuyendung", "viec-lam", "vieclam", "index", "list",
}

GENERIC_ANCHOR_TEXT = {
    "apply", "apply now", "view", "view job", "view details", "learn more",
    "details", "xem chi tiet", "xem them", "ung tuyen", "chi tiet",
    "apply here", "read more", "tim hieu them",
}

LOCATION_HINT_TOKENS = ("location", "place", "city", "dia-diem", "diadiem", "khu-vuc")

MIN_TITLE_LEN = 4
MAX_TITLE_LEN = 140


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_job_link(href: str, extra_keywords: tuple) -> bool:
    if not href:
        return False
    if href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return False

    parsed = urlparse(href)
    path_lower = parsed.path.lower()
    segments = [s for s in path_lower.strip("/").split("/") if s]
    if not segments:
        return False

    keywords = DEFAULT_JOB_PATH_KEYWORDS + tuple(extra_keywords or ())
    has_keyword_segment = any(
        any(kw == seg or kw in seg for kw in keywords) for seg in segments
    )
    if not has_keyword_segment:
        return False

    # Có >=2 segment (path có id/slug cụ thể sau từ khoá) -> chắc chắn là job detail
    if len(segments) >= 2:
        return segments[-1] not in GENERIC_LAST_SEGMENTS

    # Chỉ 1 segment (vd "/jobs") nhưng có query id/slug -> vẫn coi là job detail
    if parsed.query and re.search(r"(?:^|&)(id|slug|jobid|positionid|jid)=", parsed.query, re.IGNORECASE):
        return True

    return False


def _has_location_hint(tag) -> bool:
    if not getattr(tag, "attrs", None):
        return False
    classes = " ".join(tag.get("class", [])).lower()
    tag_id = (tag.get("id") or "").lower()
    return any(token in classes or token in tag_id for token in LOCATION_HINT_TOKENS)


def _find_heading_text(anchor) -> str:
    for tag_name in ("h1", "h2", "h3", "h4", "h5", "strong", "b"):
        heading = anchor.find(tag_name)
        if not heading and anchor.parent:
            heading = anchor.parent.find(tag_name)
        if heading:
            text = _clean_text(heading.get_text())
            if MIN_TITLE_LEN <= len(text) <= MAX_TITLE_LEN:
                return text
    return ""


def _anchor_text_without_location(anchor) -> str:
    """Text của anchor nhưng loại phần con khớp location-hint (vd <span class="location">)
    để title không bị dính chung với location (vd "Product Manager Hồ Chí Minh")."""
    clone = copy.copy(anchor)
    for loc_el in clone.find_all(_has_location_hint):
        loc_el.decompose()
    return _clean_text(clone.get_text())


def _extract_title(anchor) -> str:
    # Ưu tiên heading rõ ràng bên trong anchor trước (chính xác hơn full text,
    # vốn có thể lẫn cả location/department nếu chúng nằm cùng thẻ <a>)
    heading = anchor.find(("h1", "h2", "h3", "h4", "h5", "strong", "b"))
    if heading:
        text = _clean_text(heading.get_text())
        if MIN_TITLE_LEN <= len(text) <= MAX_TITLE_LEN:
            return text

    text = _anchor_text_without_location(anchor)
    if text and text.lower() not in GENERIC_ANCHOR_TEXT and MIN_TITLE_LEN <= len(text) <= MAX_TITLE_LEN:
        return text

    heading_text = _find_heading_text(anchor)
    if heading_text:
        return heading_text

    title_attr = _clean_text(anchor.get("title", ""))
    if MIN_TITLE_LEN <= len(title_attr) <= MAX_TITLE_LEN:
        return title_attr

    return text  # fallback: trả nguyên text dù ngắn/rỗng, sẽ bị lọc ở caller nếu rỗng


def _find_location_near(anchor) -> str:
    # Tìm trong chính anchor trước (location thường nằm ngay trong thẻ <a> của job
    # card), chỉ mới đi lên cha nếu không thấy — tránh vô tình match location của
    # job card khác (anh/em) khi đi lên quá sớm.
    node = anchor
    for _ in range(5):
        if node is None:
            break
        for candidate in node.find_all(_has_location_hint):
            text = _clean_text(candidate.get_text())
            if text and len(text) < 80:
                return text
        node = node.parent

    return ""


def extract_jobs_from_html(html: str, base_url: str, company: str, extra_keywords: tuple = ()) -> list[dict]:
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    seen_urls = set()
    jobs = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not _looks_like_job_link(href, extra_keywords):
            continue

        abs_url = urljoin(base_url, href)
        if abs_url in seen_urls:
            continue

        title = _extract_title(anchor)
        if not title or len(title) < MIN_TITLE_LEN:
            continue

        location = _find_location_near(anchor)

        seen_urls.add(abs_url)
        jobs.append({
            "company": company,
            "title": title,
            "url": abs_url,
            "location": location,
            "department": "",
            "description": "",
        })

    return jobs
