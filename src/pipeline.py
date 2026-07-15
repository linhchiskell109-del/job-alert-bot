"""Pipeline xử lý 1 công ty:

0. Kiểm tra URL career có truy cập được không — nếu KHÔNG, log cảnh báo và BỎ QUA
   công ty này ngay (không tự đoán URL khác, không chạy tiếp các bước sau).
1. Auto-detect ATS (Workday/Greenhouse/Lever/SmartRecruiters/Avature/SAP
   SuccessFactors/Oracle Recruiting) từ URL — nếu là ATS có adapter (Workday/
   Greenhouse/Lever/SmartRecruiters/Avature/SuccessFactors), dùng thẳng
   adapter đó (nhanh, ổn định, ít nguy cơ nhặt nhầm nav link hơn heuristic
   chung). Oracle Recruiting được NHẬN DIỆN (log rõ) nhưng chưa có adapter tin
   cậy, nên route tiếp xuống bước 2.
2. Company-specific parser (nếu công ty có khai báo trong
   COMPANY_PARSER_OVERRIDES bên dưới — dùng cho site JS SPA chưa xác định
   được ATS/API, cần lọc NGHIÊM NGẶT HƠN heuristic chung để tránh nhặt nhầm
   nav link, xem scrapers/strict_html.py).
3. html_scraper (requests + BeautifulSoup, heuristic tự nhận diện job link) —
   LUÔN được thử trước khi dùng trình duyệt thật, vì rẻ và nhanh hơn nhiều.
4. Nếu html_scraper trả về 0 job -> fallback playwright_scraper (render JS rồi áp
   dụng CÙNG heuristic).
5. Normalize -> Validate -> Location prefilter: MỌI job từ bất kỳ nguồn nào ở
   trên (ATS/company parser/html/playwright) đều đi qua:
     a. normalize_job() — tách title/location/employment_type từ text thô,
        KHÔNG BAO GIỜ loại job chỉ vì thiếu location/country (gán "Unknown").
     b. validate_job() — loại nav/menu page, job thiếu field bắt buộc
        (title/url).
     c. _location_allowed() — loại SỚM (ngay trong bước scraping, TRƯỚC khi
        vào matching engine) job có location RÕ RÀNG không thuộc
        `allowed_locations` (vd "Singapore", "Boston", "Lisbon"). Job có
        location "Unknown"/trống KHÔNG bị loại ở đây (không đủ căn cứ để nói
        "rõ ràng ở nước khác") — nhường lại cho matching engine cân nhắc.
   Đây là lớp bảo vệ ĐỘC LẬP với parser, nên dù 1 parser nào đó (kể cả tương
   lai) lỡ nhặt nhầm nav link hay job ở nước khác, vẫn bị chặn lại ở đây,
   không bao giờ tới được matching engine.

Không có bước nào trong pipeline này yêu cầu người dùng khai báo CSS selector hay
loại ATS thủ công, và không có bước nào tự tạo ra URL/domain không có thật.

Ngoài ra, module này hỗ trợ "shared portal" — 1 trang career dùng chung cho nhiều
brand/công ty (vd VNG + ZaloPay cùng đăng trên career.vng.com.vn): scrape MỘT LẦN
rồi phân loại job theo brand bằng từ khoá, thay vì crawl cùng 1 trang nhiều lần.
"""
import re

from ats_detector import DETECTED_ONLY_ATS, detect
from normalize import normalize_job
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

ATS_ADAPTERS = {
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "avature": avature.fetch,
    "successfactors": successfactors_csb.fetch,
}

# Công ty cần parser "nghiêm ngặt hơn" heuristic mặc định (career site render
# JS, chưa xác định được ATS/API public — xem scrapers/strict_html.py). Được
# thử SAU bước ATS detect, TRƯỚC khi rơi xuống html_scraper/playwright mặc
# định. Key phải khớp CHÍNH XÁC "name" trong config.yaml.
COMPANY_PARSER_OVERRIDES = {
    "Boston Consulting Group (BCG)": strict_html.fetch,
    "The Coca-Cola Company": strict_html.fetch,
    "Techcombank": strict_html.fetch,
    "VNG Careers Portal": strict_html.fetch,  # shared portal — xem run_for_shared_portal(); key phải khớp "name" của portal, không phải brand "VNG"
}


def _contains_word(haystack_norm: str, phrase: str) -> bool:
    phrase_norm = normalize(phrase)
    if not phrase_norm:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase_norm) + r"(?![a-z0-9])"
    return re.search(pattern, haystack_norm) is not None


def _location_allowed(job: dict, allowed_locations: tuple) -> bool:
    """EARLY location filter — chạy trong lúc scraping, TRƯỚC matching engine.
    Job "Unknown"/trống location (không đủ căn cứ để nói "rõ ràng ở nước
    khác") LUÔN được giữ lại — chỉ loại khi location/title nói RÕ 1 nơi không
    thuộc allowed_locations. `allowed_locations` rỗng -> không lọc gì cả."""
    if not allowed_locations:
        return True

    location = str(job.get("location", "") or "").strip()
    country = str(job.get("country", "") or "").strip()
    if not location or normalize(location) == normalize("Unknown"):
        if not country:
            return True  # không có thông tin -> không loại

    haystack = normalize(f"{job.get('title', '')} {location} {country}")
    return any(_contains_word(haystack, loc) for loc in allowed_locations)


def _postprocess(jobs: list, company: str, allowed_locations: tuple = ()) -> list:
    """Normalize -> Validate -> Location prefilter — bước cuối cùng trước khi
    job rời khỏi pipeline scraping, áp dụng ĐỒNG NHẤT cho MỌI nguồn (ATS/
    company parser/html/playwright). Job bị loại ở bước nào cũng được log rõ
    lý do để dễ debug scraper."""
    result = []
    for job in jobs:
        normalized = normalize_job(job)

        validation = validate_job(normalized)
        if not validation.is_valid:
            title_preview = (job.get("title") or "")[:60]
            print(f"  [DISCARD] {company} — \"{title_preview}\" -> {validation.reason}")
            continue

        if not _location_allowed(normalized, allowed_locations):
            title_preview = normalized.get("title", "")[:60]
            loc_preview = normalized.get("location", "")
            print(f"  [DISCARD] {company} — \"{title_preview}\" -> location_not_allowed ({loc_preview})")
            continue

        result.append(normalized)

    return result


def run_for_company(company_cfg: dict, extra_keywords: tuple = (),
                     allowed_locations: tuple = ()) -> tuple[list[dict], str]:
    """Trả về (jobs, method_used). method_used dùng để log — giúp biết công ty nào
    đang phải fallback Playwright (tốn tài nguyên hơn), hoặc URL nào bị chết,
    không phải để người dùng cấu hình lại gì cả. Jobs trả về LUÔN đã qua
    Normalize + Validate + Location prefilter (xem _postprocess)."""
    name = company_cfg["name"]
    url = company_cfg["url"]

    if not is_url_reachable(url):
        print(f"[WARN] {name}: career URL không truy cập được ({url}) — bỏ qua công ty này (không tự đoán URL khác)")
        return [], "unreachable"

    # Escape hatch tuỳ chọn: nếu người dùng đã biết chắc ATS (vd từ lần chạy trước
    # log ra), có thể khai báo thẳng trong config.yaml để bỏ qua bước auto-detect
    # (nhanh hơn 1 request). Hoàn toàn không bắt buộc.
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
            if jobs:
                return _postprocess(jobs, name, allowed_locations), ats
        except Exception as e:
            print(f"[WARN] {name}: adapter '{ats}' lỗi ({e}) -> fallback parser khác")

    if name in COMPANY_PARSER_OVERRIDES:
        try:
            jobs = COMPANY_PARSER_OVERRIDES[name](url, name, extra_keywords)
            if jobs:
                return _postprocess(jobs, name, allowed_locations), "company_parser"
        except Exception as e:
            print(f"[WARN] {name}: company-specific parser lỗi ({e}) -> fallback HTML scraper")

    try:
        jobs = html_scraper.fetch(url, name, extra_keywords)
    except Exception as e:
        print(f"[WARN] {name}: html_scraper lỗi ({e})")
        jobs = []

    if jobs:
        return _postprocess(jobs, name, allowed_locations), "html"

    try:
        jobs = playwright_scraper.fetch(url, name, extra_keywords)
        return _postprocess(jobs, name, allowed_locations), ("playwright" if jobs else "none")
    except Exception as e:
        print(f"[ERROR] {name}: playwright fallback cũng lỗi ({e})")
        return [], "none"


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
    """Scrape 1 portal dùng chung cho nhiều brand MỘT LẦN, rồi phân loại job theo
    brand. Trả về dict {company_name: [jobs]} — mỗi brand khai báo trong
    portal_cfg['brands'] luôn có key trong dict trả về (kể cả khi 0 job) để
    main.py log đầy đủ. Jobs đã qua Normalize + Validate + Location prefilter
    từ run_for_company() trước khi được phân loại brand ở đây."""
    name = portal_cfg["name"]
    url = portal_cfg["url"]
    brands = portal_cfg["brands"]

    jobs, method = run_for_company({"name": name, "url": url}, extra_keywords, allowed_locations)
    print(f"[{method.upper():10}] {name} (shared portal): {len(jobs)} job(s) hợp lệ, đang phân loại theo brand...")

    result = {brand["company"]: [] for brand in brands}
    for job in jobs:
        brand_company = classify_job_brand(job, brands)
        result.setdefault(brand_company, []).append({**job, "company": brand_company})

    for company_name, company_jobs in result.items():
        print(f"  -> {company_name}: {len(company_jobs)} job(s)")

    return result
