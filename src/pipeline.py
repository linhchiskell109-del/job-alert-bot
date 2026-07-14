"""Pipeline xử lý 1 công ty:
1. Auto-detect ATS (Workday/Greenhouse/Lever) từ URL — nếu có, dùng API JSON công
   khai của ATS đó (nhanh, ổn định, không cần parse HTML).
2. Nếu không phải ATS đã biết (hoặc adapter lỗi/rỗng) -> thử html_scraper (requests
   + BeautifulSoup, heuristic tự nhận diện job link).
3. Nếu html_scraper trả về 0 job -> fallback playwright_scraper (render JS rồi áp
   dụng CÙNG heuristic).

Không có bước nào trong pipeline này yêu cầu người dùng khai báo CSS selector hay
loại ATS thủ công.
"""
from ats_detector import detect
from scrapers import workday, greenhouse, lever, html_scraper, playwright_scraper

ATS_ADAPTERS = {
    "workday": workday.fetch,
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
}


def run_for_company(company_cfg: dict, extra_keywords: tuple = ()) -> tuple[list[dict], str]:
    """Trả về (jobs, method_used). method_used dùng để log — giúp biết công ty nào
    đang phải fallback Playwright (tốn tài nguyên hơn), không phải để người dùng
    cấu hình lại gì cả."""
    name = company_cfg["name"]
    url = company_cfg["url"]

    # Escape hatch tuỳ chọn: nếu người dùng đã biết chắc ATS (vd từ lần chạy trước
    # log ra), có thể khai báo thẳng trong config.yaml để bỏ qua bước auto-detect
    # (nhanh hơn 1 request). Hoàn toàn không bắt buộc.
    forced = company_cfg.get("ats_hint")
    if forced and forced in ATS_ADAPTERS:
        ats, params = forced, company_cfg.get("ats_params", {})
    else:
        match = detect(url)
        ats, params = match.ats, match.params

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
