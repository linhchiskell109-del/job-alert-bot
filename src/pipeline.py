"""Pipeline xử lý 1 công ty:

0a. Navigation Engine (src/navigation/) — CHỈ chạy khi `strategy` là "landing"
    hoặc "search". Thực thi dãy action cấu hình (click_text/click_css/...) để
    đi từ entry_url tới trang job listing/search thật, trả về URL đã điều
    hướng tới. Company `strategy: "direct"` (mặc định) BỎ QUA bước này hoàn
    toàn — dùng thẳng entry_url, HÀNH VI Y HỆT trước khi có Navigation Engine
    (backward compatible).
0b. Kiểm tra URL (đã resolve, nếu có) có truy cập được không — nếu KHÔNG, log
    cảnh báo và BỎ QUA công ty này ngay (không tự đoán URL khác).
1. Auto-detect ATS (Workday/Greenhouse/Lever/SmartRecruiters/Avature/SAP
   SuccessFactors/Oracle Recruiting) từ URL đã resolve — nếu là ATS có adapter,
   dùng thẳng adapter đó. Oracle Recruiting được NHẬN DIỆN (log rõ) nhưng chưa
   có adapter tin cậy, nên route tiếp xuống bước 2.
2. Company-specific parser (COMPANY_PARSER_OVERRIDES — site JS SPA chưa xác
   định được ATS/API, cần lọc NGHIÊM NGẶT HƠN heuristic chung).
3. html_scraper — LUÔN thử trước Playwright vì rẻ và nhanh hơn nhiều.
4. Nếu html_scraper trả về 0 job -> fallback playwright_scraper.
5. Mỗi job THÔ (dù từ nguồn nào) được bọc thành 1 JobTrace (xem job_trace.py) —
   Normalize -> Validate -> Location prefilter. Job bị loại ở bước nào cũng
   NHẬN 1 TERMINAL STATUS rõ ràng ngay tại đây (REJECTED_VALIDATION/
   REJECTED_LOCATION), KHÔNG bị lặng lẽ biến mất. Job qua được cả 2 bước vẫn
   giữ status "NORMALIZED" (chưa terminal) để main.py tiếp tục đưa vào matching
   engine.

QUAN TRỌNG: Navigation Engine CHỈ đưa trình duyệt tới đúng URL rồi ĐÓNG session
lại (trừ khi 1 parser tương lai cần keep_session=True) — parser hiện có (ATS
adapter/html_scraper/playwright_scraper) hoàn toàn KHÔNG đổi, vẫn nhận URL
string và tự fetch như trước, chỉ khác là URL đó đã được điều hướng tới thay vì
là entry_url gốc.

Không có bước nào trong pipeline này yêu cầu người dùng khai báo CSS selector hay
loại ATS thủ công (trừ khi công ty đó dùng strategy=landing với action cần
selector — khai báo trong config.yaml, KHÔNG hardcode trong .py), và không có
bước nào tự tạo ra URL/domain không có thật.

Hỗ trợ "shared portal" — 1 trang career dùng chung cho nhiều brand/công ty: scrape
MỘT LẦN rồi phân loại TỪNG JobTrace theo brand bằng từ khoá, thay vì crawl lại.
"""
import re
from dataclasses import dataclass

from ats_detector import DETECTED_ONLY_ATS, detect
from job_trace import JobTrace, extraction_confidence
from navigation.engine import navigate as navigation_navigate
from navigation.errors import NavigationFailure, SelectorNotFound, TargetURLMismatch
from navigation.errors import Timeout as NavigationTimeout
from normalize import load_normalize_config, normalize_job
from scrapers import (
    avature,
    greenhouse,
    html_scraper,
    lever,
    playwright_scraper,
    smartrecruiters,
    strict_html,
    successfactors_csb,
    workday,
)
from textnorm import normalize
from url_utils import is_url_reachable
from validation import validate_job

STRATEGIES_REQUIRING_NAVIGATION = ("landing", "search")

ATS_ADAPTERS = {
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "avature": avature.fetch,
    "successfactors": successfactors_csb.fetch,
}

# Công ty cần parser "nghiêm ngặt hơn" heuristic mặc định (career site render
# JS, chưa xác định được ATS/API public — xem scrapers/strict_html.py). Key
# phải khớp CHÍNH XÁC "name" trong config.yaml.
COMPANY_PARSER_OVERRIDES = {
    "Boston Consulting Group (BCG)": strict_html.fetch,
    "The Coca-Cola Company": strict_html.fetch,
    "Techcombank": strict_html.fetch,
    "VNG Careers Portal": strict_html.fetch,  # shared portal — key khớp "name" của portal, không phải brand "VNG"
}

# Địa danh KHÔNG phải Việt Nam, lấy từ config/normalize.yaml (known_locations)
# — dùng làm "deny marker": khi location không trích được (Unknown) nhưng
# title nêu RÕ tên 1 nước/thành phố khác, coi như đủ căn cứ để loại — KHÁC với
# việc dùng "SEA" (nhãn phạm vi mơ hồ) để CHO QUA, ở đây chỉ dùng để LOẠI nên
# an toàn hơn nhiều.
_VIETNAM_CANONICALS = {"Ho Chi Minh City", "Hanoi", "Da Nang", "Can Tho", "Hai Phong", "Remote"}


def _foreign_title_markers() -> list:
    cfg = load_normalize_config()
    markers = []
    for canonical, synonyms in cfg.known_locations.items():
        if canonical in _VIETNAM_CANONICALS:
            continue
        markers.extend(synonyms)
        markers.append(canonical)
    return markers


def _contains_word(haystack_norm: str, phrase: str) -> bool:
    phrase_norm = normalize(phrase)
    if not phrase_norm:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase_norm) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _location_allowed(job: dict, allowed_locations: tuple) -> bool:
    """EARLY location filter — chạy trong lúc scraping, TRƯỚC matching engine.

    CHỈ xét field `location`/`country` để CHO QUA — KHÔNG BAO GIỜ xét `title`
    để cho qua. Nhiều công ty (vd Deloitte) gắn nhãn phạm vi tuyển dụng vào
    TITLE (vd "- SEA") — KHÔNG có nghĩa là nơi làm việc thật (bug thực tế đã
    xảy ra — xem MIGRATION.md v7).

    Khi location KHÔNG trích được (Unknown/trống), job vẫn được GIỮ, TRỪ KHI
    title nêu RÕ tên 1 nước/thành phố CỤ THỂ khác Việt Nam (vd "... – Indonesia").
    Đây là dùng title để LOẠI (deny), KHÔNG BAO GIỜ dùng title để CHO QUA (allow)
    — an toàn hơn nhiều vì tên nước cụ thể (không mơ hồ như "SEA") gần như chắc
    chắn không phải role VN."""
    if not allowed_locations:
        return True

    location = str(job.get("location", "") or "").strip()
    country = str(job.get("country", "") or "").strip()

    if (not location or normalize(location) == normalize("Unknown")) and not country:
        title = str(job.get("title", "") or "")
        title_norm = normalize(title)
        for marker in _foreign_title_markers():
            if _contains_word(title_norm, marker):
                return False
        return True

    haystack = normalize(f"{location} {country}")
    return any(_contains_word(haystack, loc) for loc in allowed_locations)


@dataclass
class ScrapeStatus:
    """Chẩn đoán CẤP CÔNG TY — phân biệt '0 job vì thật sự không có job nào'
    với '0 job vì parser/ATS lỗi' (yêu cầu 11 trong audit)."""
    method: str          # "workday"|...|"avature"|"successfactors"|"company_parser"|"html"|"playwright"|"none"|"unreachable"|"navigation_failed"
    ok: bool              # True = quá trình scrape tự nó THÀNH CÔNG (không nghĩa là có job)
    raw_count: int = 0
    detail: str = ""      # lý do cụ thể khi ok=False (exception message, "unreachable", v.v.)


def _resolve_entry_url(company_cfg: dict) -> tuple:
    """Chạy Navigation Engine nếu strategy cần điều hướng. Trả về
    (resolved_url, nav_warning, failure_status):
      - strategy KHÔNG cần điều hướng ("direct"/"api"/không khai báo) ->
        (url gốc, "", None).
      - Điều hướng THÀNH CÔNG và khớp target_url (hoặc không cấu hình
        target_url) -> (final_url, "", None).
      - TargetURLMismatch -> (final_url THỰC TẾ, "<cảnh báo>", None) — KHÔNG
        fatal, vẫn dùng final_url thực tế vì đáng tin hơn config có thể đã cũ
        (site đổi cấu trúc); pipeline log cảnh báo rõ ràng thay vì âm thầm.
      - Lỗi khác (SelectorNotFound/Timeout/NavigationFailure — bao gồm config
        thiếu selector) -> (None, "", ScrapeStatus lỗi) — FATAL, công ty này bị
        bỏ qua lần chạy này, lý do được ghi rõ trong ScrapeStatus.detail."""
    strategy = (company_cfg.get("strategy") or "direct").lower()
    url = company_cfg["url"]

    if strategy not in STRATEGIES_REQUIRING_NAVIGATION:
        return url, "", None

    steps = company_cfg.get("navigation", [])
    target_url = company_cfg.get("target_url")
    retries = company_cfg.get("navigation_retries")
    kwargs = {"target_url": target_url}
    if retries is not None:
        kwargs["retries"] = retries

    try:
        result = navigation_navigate(url, steps, **kwargs)
        return result.final_url, "", None
    except TargetURLMismatch as e:
        final_url = getattr(e, "final_url", None)
        if not final_url:
            # Không có final_url kèm theo (không nên xảy ra với thiết kế hiện
            # tại, nhưng phòng hờ) -> coi như fatal, không đoán URL nào khác.
            return None, "", ScrapeStatus("navigation_failed", ok=False, detail=f"TargetURLMismatch (không rõ final_url): {e}")
        return final_url, f"TargetURLMismatch: {e}", None
    except SelectorNotFound as e:
        return None, "", ScrapeStatus("navigation_failed", ok=False, detail=f"SelectorNotFound: {e}")
    except NavigationTimeout as e:
        return None, "", ScrapeStatus("navigation_failed", ok=False, detail=f"Timeout: {e}")
    except NavigationFailure as e:
        return None, "", ScrapeStatus("navigation_failed", ok=False, detail=f"NavigationFailure: {e}")


def _trace_raw_jobs(raw_jobs: list, company: str, allowed_locations: tuple) -> list:
    """Bọc MỌI job thô thành JobTrace, chạy Normalize -> Validate -> Location
    prefilter. Job bị loại ở bước nào cũng nhận NGAY 1 terminal status — không
    job nào rời khỏi hàm này mà không có status rõ ràng."""
    traces = []
    for raw in raw_jobs:
        title = str(raw.get("title", "") or "")
        url = str(raw.get("url", "") or "")
        trace = JobTrace(company=company, title=title, url=url)

        normalized = normalize_job(raw)
        trace.job = normalized
        trace.confidence = extraction_confidence(normalized)
        trace.set_status("NORMALIZED")

        validation = validate_job(normalized)
        if not validation.is_valid:
            trace.set_status("REJECTED_VALIDATION", validation.reason)
            traces.append(trace)
            continue

        if not _location_allowed(normalized, allowed_locations):
            trace.set_status("REJECTED_LOCATION", f"location={normalized.get('location', '')}")
            traces.append(trace)
            continue

        # Chưa terminal — sẵn sàng cho main.py đưa vào matching engine.
        traces.append(trace)

    return traces


def run_for_company(company_cfg: dict, extra_keywords: tuple = (),
                     allowed_locations: tuple = ()) -> tuple:
    """Trả về (traces: list[JobTrace], scrape_status: ScrapeStatus)."""
    name = company_cfg["name"]
    attempts = []  # log các phương pháp đã thử + kết quả, để báo cáo đầy đủ khi mọi thứ đều fail

    resolved_url, nav_warning, nav_failure = _resolve_entry_url(company_cfg)
    if nav_failure is not None:
        print(f"[WARN] {name}: Navigation Engine lỗi -> {nav_failure.detail}")
        return [], nav_failure
    if nav_warning:
        print(f"[WARN] {name}: {nav_warning} — vẫn tiếp tục dùng URL thực tế điều hướng tới")
    url = resolved_url

    if not is_url_reachable(url):
        print(f"[WARN] {name}: career URL không truy cập được ({url}) — bỏ qua công ty này (không tự đoán URL khác)")
        return [], ScrapeStatus("unreachable", ok=False, detail=f"URL không truy cập được: {url}")

    forced = company_cfg.get("ats_hint")
    if forced and forced in ATS_ADAPTERS:
        ats, params = forced, company_cfg.get("ats_params", {})
    else:
        match = detect(url)
        ats, params = match.ats, match.params

    if ats in DETECTED_ONLY_ATS:
        print(f"[INFO] {name}: phát hiện ATS '{ats}' nhưng chưa có adapter tin cậy -> dùng HTML/Playwright")

    if ats in ATS_ADAPTERS:
        try:
            jobs = ATS_ADAPTERS[ats](name, params)
        except Exception as e:
            print(f"[WARN] {name}: adapter '{ats}' lỗi ({e}) -> fallback parser khác")
            attempts.append(f"ATS adapter '{ats}': lỗi ({e})")
        else:
            if jobs:
                traces = _trace_raw_jobs(jobs, name, allowed_locations)
                return traces, ScrapeStatus(ats, ok=True, raw_count=len(jobs))
            attempts.append(f"ATS adapter '{ats}': chạy OK, trả về 0 job")

    if name in COMPANY_PARSER_OVERRIDES:
        try:
            jobs = COMPANY_PARSER_OVERRIDES[name](url, name, extra_keywords)
        except Exception as e:
            print(f"[WARN] {name}: company-specific parser lỗi ({e})")
            attempts.append(f"company_parser: lỗi ({e})")
            return [], ScrapeStatus("company_parser", ok=False, detail="; ".join(attempts))
        if jobs:
            traces = _trace_raw_jobs(jobs, name, allowed_locations)
            return traces, ScrapeStatus("company_parser", ok=True, raw_count=len(jobs))
        attempts.append("company_parser: chạy OK, trả về 0 job")

    try:
        jobs = html_scraper.fetch(url, name, extra_keywords)
    except Exception as e:
        print(f"[WARN] {name}: html_scraper lỗi ({e})")
        jobs = None
        attempts.append(f"html_scraper: lỗi ({e})")
    else:
        if jobs:
            traces = _trace_raw_jobs(jobs, name, allowed_locations)
            return traces, ScrapeStatus("html", ok=True, raw_count=len(jobs))
        attempts.append("html_scraper: chạy OK, trả về 0 job")

    try:
        jobs = playwright_scraper.fetch(url, name, extra_keywords)
    except Exception as e:
        print(f"[ERROR] {name}: playwright fallback cũng lỗi ({e})")
        attempts.append(f"playwright_scraper: lỗi ({e})")
        return [], ScrapeStatus("none", ok=False, detail="; ".join(attempts))

    if jobs:
        traces = _trace_raw_jobs(jobs, name, allowed_locations)
        return traces, ScrapeStatus("playwright", ok=True, raw_count=len(jobs))

    # Mọi phương pháp đều CHẠY THÀNH CÔNG (không exception) nhưng ra 0 job —
    # phân biệt rõ với các trường hợp lỗi ở trên (yêu cầu 11 trong audit).
    attempts.append("playwright_scraper: chạy OK, trả về 0 job")
    detail = "Không tìm thấy job nào ở bất kỳ phương pháp nào (có thể công ty thật sự không có job mở, hoặc heuristic không nhận diện được cấu trúc trang). Chi tiết: " + "; ".join(attempts)
    return [], ScrapeStatus("none", ok=True, raw_count=0, detail=detail)


def classify_job_brand(job: dict, brands: list) -> str:
    """Xác định 1 job thuộc brand nào trong danh sách brand dùng chung 1 portal,
    dựa trên từ khoá xuất hiện trong title/department/description. Brand có
    `default: true` là bucket mặc định cho job không khớp từ khoá brand nào khác."""
    haystack = normalize(f"{job.get('title', '')} {job.get('department', '')} {job.get('description', '')}")

    for brand in brands:
        if brand.get("default"):
            continue
        for kw in brand.get("match_keywords", []):
            if normalize(kw) in haystack:
                return brand["company"]

    for brand in brands:
        if brand.get("default"):
            return brand["company"]

    return brands[0]["company"] if brands else job.get("company", "")


def run_for_shared_portal(portal_cfg: dict, extra_keywords: tuple = (),
                           allowed_locations: tuple = ()) -> dict:
    """Scrape 1 portal dùng chung cho nhiều brand MỘT LẦN, rồi phân loại TỪNG
    JobTrace theo brand (kể cả trace đã bị reject — job.job luôn có dữ liệu
    normalize để phân loại được). Trả về dict {brand_company: (traces, scrape_status)}
    — mỗi brand khai báo trong portal_cfg['brands'] luôn có key trong dict trả
    về (kể cả khi 0 job), dùng CHUNG scrape_status của portal vì chỉ scrape 1 lần."""
    name = portal_cfg["name"]
    url = portal_cfg["url"]
    brands = portal_cfg["brands"]

    traces, scrape_status = run_for_company({"name": name, "url": url}, extra_keywords, allowed_locations)
    print(f"[{scrape_status.method.upper():10}] {name} (shared portal): {len(traces)} job(s) hợp lệ để phân loại theo brand...")

    result = {brand["company"]: [] for brand in brands}
    for trace in traces:
        brand_company = classify_job_brand(trace.job or {}, brands)
        trace.company = brand_company
        result.setdefault(brand_company, []).append(trace)

    for company_name, company_traces in result.items():
        print(f"  -> {company_name}: {len(company_traces)} job(s)")

    return {company_name: (company_traces, scrape_status) for company_name, company_traces in result.items()}
