"""Entry point: fetch song song nhiều công ty + shared portal (ThreadPoolExecutor)
-> lọc job mới + match tiêu chí -> gửi email gộp -> lưu state.

LƯU Ý: logic lọc (filters.job_matches), state (is_new/mark_seen/save_state) và
gửi email (notifier.send_email) giữ NGUYÊN như trước — phần thay đổi duy nhất ở
file này là hỗ trợ thêm "shared_portals" (1 portal cho nhiều brand/công ty)."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from filters import job_matches
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
    return {"kind": "company", "name": name, "jobs": jobs, "method": method}


def process_shared_portal(portal_cfg: dict, extra_keywords: tuple) -> dict:
    name = portal_cfg["name"]
    try:
        jobs_by_brand = run_for_shared_portal(portal_cfg, extra_keywords)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        jobs_by_brand = {b["company"]: [] for b in portal_cfg.get("brands", [])}
    return {"kind": "portal", "name": name, "jobs_by_brand": jobs_by_brand}


def _collect_new_matched(jobs: list, state: dict, config: dict, sink: list):
    """Logic gốc, không đổi: job mới (chưa có trong state) + match tiêu chí ->
    thêm vào sink; mọi job (match hay không) đều được mark_seen để lần sau không
    xét lại."""
    for job in jobs:
        if not is_new(state, job):
            continue
        mark_seen(state, job)
        if job_matches(job, config):
            sink.append(job)


def main():
    config = load_config()
    state = load_state()
    extra_keywords = tuple(config.get("extra_job_url_keywords", []))
    companies = config["companies"]
    shared_portals = config.get("shared_portals", [])

    total_targets = len(companies) + len(shared_portals)
    print(f"Bắt đầu quét {len(companies)} công ty + {len(shared_portals)} shared portal "
          f"(song song, {MAX_WORKERS} workers)...\n")

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
                _collect_new_matched(jobs, state, config, all_new_matched)
            else:  # kind == "portal": đã log chi tiết từng brand trong pipeline.run_for_shared_portal
                for brand_jobs in outcome["jobs_by_brand"].values():
                    _collect_new_matched(brand_jobs, state, config, all_new_matched)

    print(f"\nPhương pháp scrape đã dùng (công ty độc lập): {method_counts}")
    print(f"Tổng cộng {len(all_new_matched)} job MỚI và MATCH tiêu chí.")

    if all_new_matched:
        send_email(all_new_matched)
    else:
        print("Không có job mới phù hợp lần này.")

    save_state(state)


if __name__ == "__main__":
    main()
