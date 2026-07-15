"""Entry point: fetch song song nhiều công ty + shared portal (ThreadPoolExecutor)
-> semantic matching (MỌI job, kể cả đã seen) -> duplicate detection -> notify
-> gửi email gộp -> lưu state.

Pipeline order (v4) — ĐÃ ĐỔI so với trước:

    Scrape
    -> Semantic matching (industry / function / level / score / explanation)
    -> Duplicate detection
    -> Notification

Trước đây duplicate detection nằm NGAY SAU scrape (job đã seen bị skip hoàn
toàn, không chạy matching). Giờ MỌI job scrape được đều chạy qua matching
engine trước — duplicate detection chỉ còn tác dụng quyết định "job này có
được GỬI EMAIL hay không", không còn quyết định "job này có được PHÂN TÍCH hay
không". Điều này giúp debug table/summary phản ánh đúng chất lượng matching
trên toàn bộ dữ liệu scrape được, không bị "che" bởi duplicate.

Matching có 2 chế độ, chọn qua `matching_engine` trong config.yaml:
  - "semantic" (mặc định, khuyến nghị) -> matching/engine.py: semantic career
    matching engine data-driven (industry/function/level/score), xem
    config/taxonomy.yaml + config/scoring.yaml.
  - "legacy" -> filters.job_matches cũ (keyword/level/location PASS-FAIL), giữ
    lại để backward-compat / rollback nhanh nếu cần.

Debug mode: đặt biến môi trường DEBUG_IGNORE_DUPLICATES=true (hoặc
`debug_ignore_duplicates: true` trong config.yaml) để bỏ qua hoàn toàn
state.json — coi MỌI job scrape được là "mới", vẫn chạy đầy đủ semantic
matching + scoring, nhưng KHÔNG đọc/ghi state.json thật (không ảnh hưởng dữ
liệu production). Dùng để test/tune matching engine mà không sợ "đốt" state.

Gửi email (notifier.send_email) giữ NGUYÊN như trước."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from filters import job_matches
from matching.engine import evaluate_job
from matching.report import MatchReport
from matching.taxonomy import load_company_overrides, load_scoring, load_taxonomy
from notifier import send_email
from pipeline import run_for_company, run_for_shared_portal
from state import is_new, load_state, mark_seen, save_state

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))


def _debug_ignore_duplicates(config: dict) -> bool:
    """DEBUG_IGNORE_DUPLICATES (env var) thắng config.yaml nếu có set — tiện để
    bật/tắt nhanh khi chạy tay (`DEBUG_IGNORE_DUPLICATES=true python src/main.py`)
    mà không cần sửa file. Không set gì -> mặc định false (hành vi production)."""
    env_val = os.environ.get("DEBUG_IGNORE_DUPLICATES")
    if env_val is not None:
        return env_val.strip().lower() in ("1", "true", "yes", "on")
    return bool(config.get("debug_ignore_duplicates", False))


def _build_engine_ctx() -> dict:
    """Load 1 lần duy nhất cho cả lần chạy: taxonomy (industry/function/level)
    + scoring weights + company overrides — tất cả từ file YAML trong config/,
    không có gì hard-code trong .py (xem matching/taxonomy.py)."""
    return {
        "taxonomy": load_taxonomy(),
        "scoring": load_scoring(),
        "overrides": load_company_overrides(),
    }


def process_company(company_cfg: dict, extra_keywords: tuple, allowed_locations: tuple) -> dict:
    name = company_cfg["name"]
    try:
        jobs, method = run_for_company(company_cfg, extra_keywords, allowed_locations)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        jobs, method = [], "error"
    return {"kind": "company", "name": name, "jobs": jobs, "method": method, "company_cfg": company_cfg}


def process_shared_portal(portal_cfg: dict, extra_keywords: tuple, allowed_locations: tuple) -> dict:
    name = portal_cfg["name"]
    try:
        jobs_by_brand = run_for_shared_portal(portal_cfg, extra_keywords, allowed_locations)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        jobs_by_brand = {b["company"]: [] for b in portal_cfg.get("brands", [])}
    return {"kind": "portal", "name": name, "jobs_by_brand": jobs_by_brand}


def _process_job(job: dict, company_cfg: dict, config: dict, state: dict,
                  engine_ctx: dict, report: MatchReport, sink: list,
                  debug_ignore_duplicates: bool):
    """Xử lý ĐÚNG 1 job theo pipeline mới:
    1. Semantic matching (luôn chạy, bất kể job đã seen hay chưa)
    2. Duplicate detection (chỉ để quyết định notify — KHÔNG ảnh hưởng bước 1)
    3. Notify = accepted AND NOT duplicate
    Ở chế độ debug (debug_ignore_duplicates=True): duplicate LUÔN False, và
    KHÔNG đụng vào `state` thật (không gọi mark_seen) — state truyền vào lúc
    đó là 1 dict rỗng dùng riêng cho lần chạy debug, xem main()."""
    company_name = company_cfg.get("name", job.get("company", ""))
    title = job.get("title", "")

    # ---- 1. Semantic matching (luôn chạy trước, không phụ thuộc duplicate) ----
    if config.get("matching_engine", "semantic") == "legacy":
        accepted = job_matches(job, config)
        add_row = lambda duplicate, notify: report.add_legacy(company_name, title, accepted, duplicate, notify)
        match_score, match_reason = (100.0 if accepted else 0.0), ("accepted" if accepted else "keyword")
    else:
        result = evaluate_job(
            job, company_cfg, config.get("locations", []),
            engine_ctx["taxonomy"], engine_ctx["scoring"], engine_ctx["overrides"],
        )
        accepted = result.accepted
        add_row = lambda duplicate, notify: report.add(company_name, title, result, duplicate, notify)
        match_score, match_reason = result.score, result.reason_detail

    # ---- 2. Duplicate detection (chỉ gate notify, không gate matching ở trên) ----
    if debug_ignore_duplicates:
        duplicate = False
    else:
        duplicate = not is_new(state, job)
        mark_seen(state, job)  # luôn đánh dấu đã thấy, dù accept/reject/duplicate

    # ---- 3. Notify ----
    notify = accepted and not duplicate

    add_row(duplicate, notify)

    if notify:
        sink.append({**job, "match_score": match_score, "match_reason": match_reason})


def _process_jobs(jobs: list, company_cfg: dict, config: dict, state: dict,
                   engine_ctx: dict, report: MatchReport, sink: list,
                   debug_ignore_duplicates: bool):
    for job in jobs:
        _process_job(job, company_cfg, config, state, engine_ctx, report, sink, debug_ignore_duplicates)


def main():
    config = load_config()
    extra_keywords = tuple(config.get("extra_job_url_keywords", []))
    allowed_locations = tuple(config.get("locations", []))
    companies = config["companies"]
    shared_portals = config.get("shared_portals", [])
    engine_ctx = _build_engine_ctx()
    report = MatchReport()

    debug_mode = _debug_ignore_duplicates(config)
    # Debug mode: KHÔNG đọc state.json thật, dùng state rỗng riêng cho lần chạy
    # này, và sẽ KHÔNG save_state ở cuối -> không ảnh hưởng production.
    state = {"seen": {}} if debug_mode else load_state()

    mode = config.get("matching_engine", "semantic")
    print(f"Bắt đầu quét {len(companies)} công ty + {len(shared_portals)} shared portal "
          f"(song song, {MAX_WORKERS} workers, matching_engine={mode}"
          f"{', DEBUG_IGNORE_DUPLICATES=true' if debug_mode else ''})...\n")

    all_new_matched = []
    method_counts = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_company, c, extra_keywords, allowed_locations) for c in companies]
        futures += [executor.submit(process_shared_portal, p, extra_keywords, allowed_locations) for p in shared_portals]

        for future in as_completed(futures):
            outcome = future.result()

            if outcome["kind"] == "company":
                method = outcome["method"]
                jobs = outcome["jobs"]
                method_counts[method] = method_counts.get(method, 0) + 1
                print(f"[{method.upper():10}] {outcome['name']}: {len(jobs)} job(s)")
                _process_jobs(jobs, outcome["company_cfg"], config, state,
                              engine_ctx, report, all_new_matched, debug_mode)
            else:  # kind == "portal": đã log chi tiết từng brand trong pipeline.run_for_shared_portal
                for brand_name, brand_jobs in outcome["jobs_by_brand"].items():
                    _process_jobs(brand_jobs, {"name": brand_name}, config, state,
                                  engine_ctx, report, all_new_matched, debug_mode)

    print(f"\nPhương pháp scrape đã dùng (công ty độc lập): {method_counts}")
    report.print_table()
    report.print_summary()
    print(f"\nTổng cộng {len(all_new_matched)} job sẽ được gửi thông báo.")

    if all_new_matched:
        send_email(all_new_matched)
    else:
        print("Không có job mới phù hợp lần này.")

    if debug_mode:
        print("\n[DEBUG] DEBUG_IGNORE_DUPLICATES=true -> KHÔNG lưu state.json (không ảnh hưởng production).")
    else:
        save_state(state)


if __name__ == "__main__":
    main()
