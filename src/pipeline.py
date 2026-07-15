"""Pipeline xử lý 1 công ty:
0. Kiểm tra URL career có truy cập được không — nếu KHÔNG, log cảnh báo và BỎ QUA
   công ty này ngay (không tự đoán URL khác, không chạy tiếp các bước sau).
1. Auto-detect ATS (Workday/Greenhouse/Lever/SmartRecruiters/SAP SuccessFactors/
   Oracle Recruiting) từ URL — nếu là ATS có adapter public API (Workday/
   Greenhouse/Lever/SmartRecruiters), dùng thẳng API đó (nhanh, ổn định, không
   cần parse HTML). SuccessFactors/Oracle Recruiting được NHẬN DIỆN (log rõ) nhưng
   không có adapter public API tin cậy, nên route tiếp xuống bước 2.
2. html_scraper (requests + BeautifulSoup, heuristic tự nhận diện job link) —
   LUÔN được thử trước khi dùng trình duyệt thật, vì rẻ và nhanh hơn nhiều.
3. Nếu html_scraper trả về 0 job -> fallback playwright_scraper (render JS rồi áp
   dụng CÙNG heuristic).

Không có bước nào trong pipeline này yêu cầu người dùng khai báo CSS selector hay
loại ATS thủ công, và không có bước nào tự tạo ra URL/domain không có thật.

Ngoài ra, module này hỗ trợ "shared portal" — 1 trang career dùng chung cho nhiều
brand/công ty (vd VNG + ZaloPay cùng đăng trên career.vng.com.vn): scrape MỘT LẦN
rồi phân loại job theo brand bằng từ khoá, thay vì crawl cùng 1 trang nhiều lần.
"""
from ats_detector import DETECTED_ONLY_ATS, detect
from scrapers import greenhouse, html_scraper, lever, playwright_scraper, smartrecruiters, workday
from textnorm import normalize
from url_utils import is_url_reachable

ATS_ADAPTERS = {
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "smartrecruiters": smartrecruiters.fetch,
}


def run_for_company(company_cfg: dict, extra_keywords: tuple = ()) -> tuple[list[dict], str]:
    """Trả về (jobs, method_used). method_used dùng để log — giúp biết công ty nào
    đang phải fallback Playwright (tốn tài nguyên hơn), hoặc URL nào bị chết,
    không phải để người dùng cấu hình lại gì cả."""
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
        print(f"[INFO] {name}: phát hiện ATS '{ats}' nhưng không có public API tin cậy -> dùng HTML/Playwright")

    if ats in ATS_ADAPTERS:
        try:
            jobs = ATS_ADAPTERS[ats](name, params)
            if jobs:
                return jobs, ats
        except Exception as e:
            print(f"[WARN] {name}: adapter '{ats}' lỗi ({e}) -> fallback HTML scraper")

    try:
        jobs = html_scraper.fetch(url, name, extra_keywords)
    except Exception as e:
        print(f"[WARN] {name}: html_scraper lỗi ({e})")
        jobs = []

    if jobs:
        return jobs, "html"

    try:
        jobs = playwright_scraper.fetch(url, name, extra_keywords)
        return jobs, ("playwright" if jobs else "none")
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


def run_for_shared_portal(portal_cfg: dict, extra_keywords: tuple = ()) -> dict:
    """Scrape 1 portal dùng chung cho nhiều brand MỘT LẦN, rồi phân loại job theo
    brand. Trả về dict {company_name: [jobs]} — mỗi brand khai báo trong
    portal_cfg['brands'] luôn có key trong dict trả về (kể cả khi 0 job) để
    main.py log đầy đủ."""
    name = portal_cfg["name"]
    url = portal_cfg["url"]
    brands = portal_cfg["brands"]

    jobs, method = run_for_company({"name": name, "url": url}, extra_keywords)
    print(f"[{method.upper():10}] {name} (shared portal): {len(jobs)} job(s) thô, đang phân loại theo brand...")

    result = {brand["company"]: [] for brand in brands}
    for job in jobs:
        brand_company = classify_job_brand(job, brands)
        result.setdefault(brand_company, []).append({**job, "company": brand_company})

    for company_name, company_jobs in result.items():
        print(f"  -> {company_name}: {len(company_jobs)} job(s)")

    return result
