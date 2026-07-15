"""Entry point: fetch song song nhiều công ty + shared portal (ThreadPoolExecutor)
-> lọc job mới + match tiêu chí -> gửi email gộp -> lưu state.

Matching có 2 chế độ, chọn qua `matching_engine` trong config.yaml:
  - "semantic" (mặc định, khuyến nghị) -> matching/engine.py: semantic career
    matching engine data-driven (industry/function/level/score), xem
    config/taxonomy.yaml + config/scoring.yaml.
  - "legacy" -> filters.job_matches cũ (keyword/level/location PASS-FAIL), giữ
    lại để backward-compat / rollback nhanh nếu cần.

State (is_new/mark_seen/save_state) và gửi email (notifier.send_email) giữ
NGUYÊN như trước."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from filters import job_matches
from matching.engine import evaluate_job
from matching.report import MatchReport, log_job_result
from matching.taxonomy import load_company_overrides, load_scoring, load_taxonomy
from notifier import send_email
from pipeline import run_for_company, run_for_shared_portal
from state import is_new, load_state, mark_seen, save_state

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))


def process_company(company_cfg: dict, extra_keywords: tuple) -> dict:
    name = company_cfg["name"]
    try:
        jobs, method = run_for_company(company_cfg, extra_keywords)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        jobs, method = [], "error"
    return {"kind": "company", "name": name, "jobs": jobs, "method": method, "company_cfg": company_cfg}


def process_shared_portal(portal_cfg: dict, extra_keywords: tuple) -> dict:
    name = portal_cfg["name"]
    try:
        jobs_by_brand = run_for_shared_portal(portal_cfg, extra_keywords)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        jobs_by_brand = {b["company"]: [] for b in portal_cfg.get("brands", [])}
    return {"kind": "portal", "name": name, "jobs_by_brand": jobs_by_brand}


def _collect_new_matched(jobs: list, state: dict, config: dict, sink: list,
                          engine_ctx: dict, report: MatchReport, company_cfg: dict):
    """Job mới (chưa có trong state) -> chấm điểm bằng matching engine -> nếu
    ACCEPT thì thêm vào sink. Mọi job (match hay không, mới hay cũ) đều được
    mark_seen để lần sau không xét lại. Mọi job MỚI (kể cả duplicate đã seen
    trước đó bị bỏ qua ở dòng đầu) đều được ghi vào `report` để có breakdown
    đầy đủ cuối lần chạy (Accepted / Duplicate / Keyword / Score too low /
    Location / Experience)."""
    for job in jobs:
        if not is_new(state, job):
            report.record_duplicate()
            continue
        mark_seen(state, job)

        if config.get("matching_engine", "semantic") == "legacy":
            if job_matches(job, config):
                report.record("accepted")
                sink.append(job)
            else:
                report.record("keyword")
            continue

        result = evaluate_job(
            job, company_cfg, config.get("locations", []),
            engine_ctx["taxonomy"], engine_ctx["scoring"], engine_ctx["overrides"],
        )
        log_job_result(company_cfg.get("name", job.get("company", "")), job, result)
        report.record_result(result)
        if result.accepted:
            sink.append({**job, "match_score": result.score, "match_reason": result.reason_detail})


def _build_engine_ctx() -> dict:
    """Load 1 lần duy nhất cho cả lần chạy: taxonomy (industry/function/level)
    + scoring weights + company overrides — tất cả từ file YAML trong config/,
    không có gì hard-code trong .py (xem matching/taxonomy.py)."""
    return {
        "taxonomy": load_taxonomy(),
        "scoring": load_scoring(),
        "overrides": load_company_overrides(),
    }


def main():
    config = load_config()
    state = load_state()
    extra_keywords = tuple(config.get("extra_job_url_keywords", []))
    companies = config["companies"]
    shared_portals = config.get("shared_portals", [])
    engine_ctx = _build_engine_ctx()
    report = MatchReport()

    mode = config.get("matching_engine", "semantic")
    print(f"Bắt đầu quét {len(companies)} công ty + {len(shared_portals)} shared portal "
          f"(song song, {MAX_WORKERS} workers, matching_engine={mode})...\n")

    all_new_matched = []
    method_counts = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_company, c, extra_keywords) for c in companies]
        futures += [executor.submit(process_shared_portal, p, extra_keywords) for p in shared_portals]

        for future in as_completed(futures):
            outcome = future.result()

            if outcome["kind"] == "company":
                method = outcome["method"]
                jobs = outcome["jobs"]
                method_counts[method] = method_counts.get(method, 0) + 1
                print(f"[{method.upper():10}] {outcome['name']}: {len(jobs)} job(s)")
                _collect_new_matched(jobs, state, config, all_new_matched,
                                      engine_ctx, report, outcome["company_cfg"])
            else:  # kind == "portal": đã log chi tiết từng brand trong pipeline.run_for_shared_portal
                for brand_name, brand_jobs in outcome["jobs_by_brand"].items():
                    _collect_new_matched(brand_jobs, state, config, all_new_matched,
                                          engine_ctx, report, {"name": brand_name})

    print(f"\nPhương pháp scrape đã dùng (công ty độc lập): {method_counts}")
    print(f"Tổng cộng {len(all_new_matched)} job MỚI và MATCH tiêu chí.")
    report.print_summary()

    if all_new_matched:
        send_email(all_new_matched)
    else:
        print("Không có job mới phù hợp lần này.")

    save_state(state)


if __name__ == "__main__":
    main()
