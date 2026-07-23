"""Entry point: fetch song song nhiều công ty + shared portal (ThreadPoolExecutor)
-> semantic matching (MỌI job, kể cả đã seen) -> duplicate detection -> notify
-> gửi email gộp -> lưu state.

Pipeline order — Scrape -> Normalize -> Validate -> Location prefilter ->
Matching -> Duplicate detection -> Notification. MỌI job crawl được đều đi qua
JobTrace (xem job_trace.py) và nhận ĐÚNG 1 terminal status — không job nào
"biến mất" khỏi log mà không rõ lý do (xem diagnostics.py).

Matching có 2 chế độ, chọn qua `matching_engine` trong config.yaml:
  - "semantic" (mặc định) -> matching/engine.py, data-driven (xem
    config/taxonomy.yaml + config/scoring.yaml).
  - "legacy" -> filters.job_matches cũ (keyword/level/location PASS-FAIL).
    LƯU Ý: legacy không phân biệt được REJECTED_FUNCTION/EXPERIENCE/SCORE —
    mọi job bị từ chối đều gắn chung status REJECTED_FUNCTION (giới hạn đã
    biết, không phải bug).

Debug mode: DEBUG_IGNORE_DUPLICATES=true (env var, ưu tiên hơn config.yaml) để
bỏ qua hoàn toàn state.json — coi MỌI job là "mới", vẫn chạy đầy đủ matching,
KHÔNG đọc/ghi state.json thật.

--debug-company "<Tên công ty>": chỉ scrape + xử lý ĐÚNG công ty đó (hoặc brand
trong shared portal), in báo cáo chi tiết per-job — dùng để debug 1 công ty mà
không phải đọc log của cả 20 công ty."""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from diagnostics import Diagnostics
from filters import job_matches
from job_trace import match_reason_to_status
from matching.engine import evaluate_job
from matching.taxonomy import load_company_overrides, load_scoring, load_taxonomy
from notifier import send_email
from pipeline import ScrapeStatus, run_for_company, run_for_shared_portal
from state import is_new, load_state, mark_seen, save_state

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))


def _debug_ignore_duplicates(config: dict) -> bool:
    env_val = os.environ.get("DEBUG_IGNORE_DUPLICATES")
    if env_val is not None:
        return env_val.strip().lower() in ("1", "true", "yes", "on")
    return bool(config.get("debug_ignore_duplicates", False))


def _build_engine_ctx() -> dict:
    return {
        "taxonomy": load_taxonomy(),
        "scoring": load_scoring(),
        "overrides": load_company_overrides(),
    }


def process_company(company_cfg: dict, extra_keywords: tuple, allowed_locations: tuple) -> dict:
    name = company_cfg["name"]
    try:
        traces, scrape_status = run_for_company(company_cfg, extra_keywords, allowed_locations)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        traces, scrape_status = [], ScrapeStatus("error", ok=False, detail=str(e))
    return {"kind": "company", "name": name, "traces": traces, "scrape_status": scrape_status}


def process_shared_portal(portal_cfg: dict, extra_keywords: tuple, allowed_locations: tuple) -> dict:
    name = portal_cfg["name"]
    try:
        jobs_by_brand = run_for_shared_portal(portal_cfg, extra_keywords, allowed_locations)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        err = ScrapeStatus("error", ok=False, detail=str(e))
        jobs_by_brand = {b["company"]: ([], err) for b in portal_cfg.get("brands", [])}
    return {"kind": "portal", "name": name, "jobs_by_brand": jobs_by_brand}


def _process_trace(trace, config: dict, state: dict, engine_ctx: dict, sink: list, debug_ignore_duplicates: bool):
    """Tiếp tục 1 JobTrace đã qua pipeline (Normalize/Validate/Location) — chạy
    Matching rồi Duplicate detection, LUÔN kết thúc bằng 1 terminal status.
    Trace đã terminal (REJECTED_VALIDATION/REJECTED_LOCATION từ pipeline.py)
    được bỏ qua — không xử lý lại."""
    if trace.is_terminal:
        return

    job = trace.job
    company_cfg = {"name": trace.company}

    if config.get("matching_engine", "semantic") == "legacy":
        accepted = job_matches(job, config)
        if not accepted:
            trace.set_status("REJECTED_FUNCTION", "legacy keyword filter — không khớp jd_keywords/levels/locations")
            return
        match_score, match_reason = 100.0, "accepted (legacy keyword filter)"
    else:
        result = evaluate_job(
            job, company_cfg, config.get("locations", []),
            engine_ctx["taxonomy"], engine_ctx["scoring"], engine_ctx["overrides"],
        )
        trace.industry = result.industry_display
        trace.function = result.function_display or "-"
        trace.level = result.level_display or "-"
        trace.score = result.score
        if not result.accepted:
            trace.set_status(match_reason_to_status(result.reason), result.reason_detail)
            return
        match_score, match_reason = result.score, result.reason_detail

    # ---- Đã MATCHED — xét duplicate (chỉ gate notify, không gate matching ở trên) ----
    if debug_ignore_duplicates:
        duplicate = False
    else:
        duplicate = not is_new(state, job)
        mark_seen(state, job)  # luôn đánh dấu đã thấy, dù accept/reject/duplicate

    if duplicate:
        trace.set_status("ALREADY_NOTIFIED", "existing notification history")
    else:
        trace.set_status("NOTIFIED", "job mới")
        sink.append({**job, "match_score": match_score, "match_reason": match_reason})


def _filter_targets(companies: list, shared_portals: list, debug_company: str) -> tuple:
    if not debug_company:
        return companies, shared_portals
    companies = [c for c in companies if c["name"] == debug_company]
    portals = [p for p in shared_portals
               if p["name"] == debug_company or any(b["company"] == debug_company for b in p.get("brands", []))]
    if not companies and not portals:
        print(f"[DEBUG] Không tìm thấy công ty/brand '{debug_company}' trong config.yaml "
              f"(kiểm tra đúng chính tả 'name' trong config.yaml)")
    return companies, portals


def main():
    arg_parser = argparse.ArgumentParser(description="Job alert bot")
    arg_parser.add_argument("--debug-company", default=None,
                             help="Chỉ scrape + xử lý 1 công ty (hoặc brand trong shared portal), in báo cáo chi tiết")
    args = arg_parser.parse_args()

    config = load_config()
    extra_keywords = tuple(config.get("extra_job_url_keywords", []))
    allowed_locations = tuple(config.get("locations", []))
    companies, shared_portals = _filter_targets(
        config["companies"], config.get("shared_portals", []), args.debug_company)
    engine_ctx = _build_engine_ctx()
    diagnostics = Diagnostics()

    debug_mode = _debug_ignore_duplicates(config)
    state = {"seen": {}} if debug_mode else load_state()

    mode = config.get("matching_engine", "semantic")
    print(f"Bắt đầu quét {len(companies)} công ty + {len(shared_portals)} shared portal "
          f"(song song, {MAX_WORKERS} workers, matching_engine={mode}"
          f"{', DEBUG_IGNORE_DUPLICATES=true' if debug_mode else ''}"
          f"{f', debug_company={args.debug_company}' if args.debug_company else ''})...\n")

    all_new_matched = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_company, c, extra_keywords, allowed_locations) for c in companies]
        futures += [executor.submit(process_shared_portal, p, extra_keywords, allowed_locations) for p in shared_portals]

        for future in as_completed(futures):
            outcome = future.result()

            if outcome["kind"] == "company":
                name, traces, scrape_status = outcome["name"], outcome["traces"], outcome["scrape_status"]
                diagnostics.add_scrape_status(name, scrape_status)
                print(f"[{scrape_status.method.upper():10}] {name}: {len(traces)} job(s) raw"
                      + ("" if scrape_status.ok else f" (LỖI: {scrape_status.detail})"))
                for t in traces:
                    _process_trace(t, config, state, engine_ctx, all_new_matched, debug_mode)
                diagnostics.add_traces(traces)
            else:  # kind == "portal"
                for brand_name, (brand_traces, scrape_status) in outcome["jobs_by_brand"].items():
                    diagnostics.add_scrape_status(brand_name, scrape_status)
                    for t in brand_traces:
                        _process_trace(t, config, state, engine_ctx, all_new_matched, debug_mode)
                    diagnostics.add_traces(brand_traces)

    diagnostics.print_company_funnel_table()
    diagnostics.print_rejection_breakdown()
    diagnostics.print_accepted_jobs()
    diagnostics.print_per_job_decisions()
    diagnostics.explain_notifications(len(all_new_matched))
    diagnostics.print_conservation_check()

    if args.debug_company:
        diagnostics.print_debug_company(args.debug_company)

    print(f"\nTổng cộng {len(all_new_matched)} job sẽ được gửi thông báo.")

    if all_new_matched:
        send_email(all_new_matched)
    else:
        print("Không có job mới phù hợp lần này.")

    if args.debug_company:
        print("\n[DEBUG] Chạy ở chế độ --debug-company -> KHÔNG lưu state.json (tránh ảnh hưởng lần chạy production thật).")
    elif debug_mode:
        print("\n[DEBUG] DEBUG_IGNORE_DUPLICATES=true -> KHÔNG lưu state.json (không ảnh hưởng production).")
    else:
        save_state(state)


if __name__ == "__main__":
    main()
