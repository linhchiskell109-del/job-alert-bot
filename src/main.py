"""Entry point: fetch song song nhiều công ty (ThreadPoolExecutor) -> lọc job mới
+ match tiêu chí -> gửi email gộp -> lưu state."""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import load_config
from filters import job_matches
from notifier import send_email
from pipeline import run_for_company
from state import is_new, load_state, mark_seen, save_state

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "6"))


def process_company(company_cfg: dict, extra_keywords: tuple) -> tuple[str, list[dict], str]:
    name = company_cfg["name"]
    try:
        jobs, method = run_for_company(company_cfg, extra_keywords)
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return name, [], "error"
    return name, jobs, method


def main():
    config = load_config()
    state = load_state()
    extra_keywords = tuple(config.get("extra_job_url_keywords", []))
    companies = config["companies"]

    print(f"Bắt đầu quét {len(companies)} công ty (song song, {MAX_WORKERS} workers)...\n")

    all_new_matched = []
    method_counts = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_company, c, extra_keywords): c
            for c in companies
        }
        for future in as_completed(futures):
            name, jobs, method = future.result()
            method_counts[method] = method_counts.get(method, 0) + 1
            print(f"[{method.upper():10}] {name}: {len(jobs)} job(s)")

            for job in jobs:
                if not is_new(state, job):
                    continue
                mark_seen(state, job)
                if job_matches(job, config):
                    all_new_matched.append(job)

    print(f"\nPhương pháp scrape đã dùng: {method_counts}")
    print(f"Tổng cộng {len(all_new_matched)} job MỚI và MATCH tiêu chí.")

    if all_new_matched:
        send_email(all_new_matched)
    else:
        print("Không có job mới phù hợp lần này.")

    save_state(state)


if __name__ == "__main__":
    main()
