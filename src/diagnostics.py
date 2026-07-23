"""Observability layer — tổng hợp JobTrace (job_trace.py) thành các báo cáo dễ
đọc: funnel theo công ty, breakdown lý do reject, danh sách job accepted (dù đã
notify hay chưa), giải thích vì sao 0 notification, và kiểm tra bất biến "không
job nào biến mất" (mục 9 trong audit).

KHÔNG chứa logic quyết định (matching/duplicate/notify) — chỉ đọc lại JobTrace
đã có status cuối cùng để trình bày, đúng tinh thần "observability tách biệt
khỏi business logic".
"""
from collections import defaultdict

from job_trace import TERMINAL_STATUSES

STATUS_LABELS = {
    "NOTIFIED": "NEW_NOTIFICATION",
    "ALREADY_NOTIFIED": "ALREADY_NOTIFIED",
    "REJECTED_VALIDATION": "REJECTED_VALIDATION",
    "REJECTED_LOCATION": "REJECTED_LOCATION",
    "REJECTED_FUNCTION": "REJECTED_FUNCTION",
    "REJECTED_EXPERIENCE": "REJECTED_EXPERIENCE",
    "REJECTED_SCORE": "REJECTED_SCORE",
}


class Diagnostics:
    def __init__(self):
        self.traces = []               # list[JobTrace] — mọi job crawl được, mọi công ty
        self.scrape_status = {}        # company -> ScrapeStatus (chẩn đoán tầng scraper)

    def add_traces(self, traces: list):
        self.traces.extend(traces)

    def add_scrape_status(self, company: str, status):
        self.scrape_status[company] = status

    def company_names(self) -> list:
        names = set(self.scrape_status.keys()) | {t.company for t in self.traces}
        return sorted(names)

    def traces_for(self, company: str) -> list:
        return [t for t in self.traces if t.company == company]

    # ---- Funnel theo công ty (yêu cầu 5 + 12) ----
    def funnel_for(self, company: str) -> dict:
        traces = self.traces_for(company)
        raw = len(traces)
        rejected_validation = sum(1 for t in traces if t.status == "REJECTED_VALIDATION")
        rejected_location = sum(1 for t in traces if t.status == "REJECTED_LOCATION")
        # "parsed" trong kiến trúc hiện tại LUÔN = raw: scraper chỉ trả về dict
        # khi đã trích được title+url (không có khái niệm "tìm thấy link nhưng
        # parse lỗi" riêng biệt) — xem MIGRATION.md phần audit observability.
        parsed = raw
        validated = raw - rejected_validation - rejected_location
        already_notified = sum(1 for t in traces if t.status == "ALREADY_NOTIFIED")
        new_notifications = sum(1 for t in traces if t.status == "NOTIFIED")
        matched = already_notified + new_notifications
        return {
            "raw": raw, "parsed": parsed, "validated": validated,
            "matched": matched, "already_notified": already_notified,
            "new_notifications": new_notifications,
        }

    # ---- Breakdown lý do reject theo công ty (yêu cầu 6) ----
    def rejection_breakdown_for(self, company: str) -> dict:
        traces = self.traces_for(company)
        counts = defaultdict(int)
        for t in traces:
            if t.status == "REJECTED_LOCATION":
                counts["location"] += 1
            elif t.status == "REJECTED_EXPERIENCE":
                counts["experience"] += 1
            elif t.status == "REJECTED_FUNCTION":
                counts["function"] += 1
            elif t.status == "REJECTED_SCORE":
                counts["score"] += 1
            elif t.status == "REJECTED_VALIDATION":
                counts["validation"] += 1
            elif t.status == "ALREADY_NOTIFIED":
                counts["duplicate"] += 1
        return dict(counts)

    # ---- In báo cáo ----
    def print_company_funnel_table(self):
        print("\n=== Company recall report (Raw -> Parsed -> Validated -> Matched -> AlreadyNotified -> NewNotifications) ===")
        header = f"{'Company':<28}{'Raw':>6}{'Parsed':>8}{'Valid':>7}{'Matched':>9}{'AlreadyNotif':>14}{'NewNotif':>10}  Scrape status"
        print(header)
        for company in self.company_names():
            f = self.funnel_for(company)
            status = self.scrape_status.get(company)
            status_label = status.method if status else "-"
            if status and not status.ok:
                status_label += f" (LỖI: {status.detail})"
            elif status and status.raw_count == 0 and f["raw"] == 0 and status.detail:
                status_label += f" ({status.detail})"
            print(f"{company:<28}{f['raw']:>6}{f['parsed']:>8}{f['validated']:>7}"
                  f"{f['matched']:>9}{f['already_notified']:>14}{f['new_notifications']:>10}  {status_label}")

    def print_rejection_breakdown(self):
        print("\n=== Rejection breakdown theo công ty ===")
        for company in self.company_names():
            breakdown = self.rejection_breakdown_for(company)
            if not breakdown:
                continue
            parts = " | ".join(f"{k}: {v}" for k, v in breakdown.items())
            print(f"{company}: {parts}")

    def print_accepted_jobs(self):
        """LUÔN in job accepted, kể cả job đã notify trước đó (yêu cầu 7) —
        không "giấu" job chỉ vì nó bị duplicate."""
        accepted = [t for t in self.traces if t.status in ("NOTIFIED", "ALREADY_NOTIFIED")]
        print(f"\n=== Accepted jobs ({len(accepted)}) ===")
        for t in accepted:
            label = "NEW_NOTIFICATION" if t.status == "NOTIFIED" else "ALREADY_NOTIFIED"
            print(f"{t.company} — \"{t.title}\" -> {label}")

    def print_per_job_decisions(self):
        """In quyết định cuối cho MỖI job đã MATCHED (accepted bởi matching
        engine) — bất kể sau đó có bị duplicate hay không (yêu cầu 4)."""
        matched = [t for t in self.traces if t.status in ("NOTIFIED", "ALREADY_NOTIFIED")]
        if not matched:
            return
        print("\n=== Per-job decisions (MATCHED) ===")
        for t in matched:
            label = "NOTIFIED" if t.status == "NOTIFIED" else "ALREADY_NOTIFIED"
            reason = "job mới" if t.status == "NOTIFIED" else "đã có trong lịch sử notify (existing notification history)"
            print(f"{t.company}\n{t.title}\nMATCHED\n  -> {label}\n  reason: {reason}\n{'-' * 36}")

    def explain_notifications(self, sent_count: int):
        """Giải thích rõ ràng thay vì chỉ in con số (yêu cầu 8)."""
        accepted = [t for t in self.traces if t.status in ("NOTIFIED", "ALREADY_NOTIFIED")]
        already = sum(1 for t in accepted if t.status == "ALREADY_NOTIFIED")
        new = sum(1 for t in accepted if t.status == "NOTIFIED")
        print(f"\n{len(accepted)} accepted jobs")
        print(f"{already} already notified")
        print(f"{new} new jobs")
        if sent_count == 0 and accepted:
            print("-> 0 notification vì TOÀN BỘ job accepted đều đã được báo ở lần chạy trước (không phải bug).")
        elif sent_count == 0 and not accepted:
            print("-> 0 notification vì không có job nào accepted lần này (xem rejection breakdown ở trên để biết vì sao).")

    # ---- Bất biến bảo toàn job (yêu cầu 9) ----
    def verify_conservation(self) -> tuple:
        """raw_jobs = validation_rejected + location_rejected + function_rejected
        + experience_rejected + score_rejected + already_notified + new_notifications.
        Đúng theo THIẾT KẾ (mỗi JobTrace được set đúng 1 terminal status), hàm
        này CHỈ verify runtime KHÔNG có trace nào bị bỏ sót (vd code path nào đó
        return sớm mà quên set status) — nếu invariant vỡ, đây là bug thật cần
        sửa ngay, không phải log tham khảo."""
        non_terminal = [t for t in self.traces if not t.is_terminal]
        total = len(self.traces)
        terminal_count = total - len(non_terminal)
        ok = len(non_terminal) == 0
        message = (
            f"Job conservation: {terminal_count}/{total} job có terminal status."
            if ok else
            f"⚠️  VI PHẠM BẤT BIẾN: {len(non_terminal)}/{total} job KHÔNG có terminal status "
            f"(status hiện tại: {sorted({t.status for t in non_terminal})}) — có job bị 'biến mất' khỏi pipeline, cần sửa code."
        )
        return ok, message

    def print_conservation_check(self):
        ok, message = self.verify_conservation()
        print(f"\n=== Job conservation check ===\n{message}")

    # ---- --debug-company (yêu cầu 15) ----
    def print_debug_company(self, company: str):
        traces = self.traces_for(company)
        status = self.scrape_status.get(company)
        print(f"\n=== DEBUG: {company} ===")
        if status:
            print(f"Scrape method: {status.method} | ok={status.ok}"
                  + (f" | detail: {status.detail}" if status.detail else ""))
        print(f"Raw jobs: {len(traces)}")
        f = self.funnel_for(company)
        print(f"After parser: {f['parsed']}")
        print(f"After validation: {f['validated']}")
        print(f"After matching: {f['matched']}")

        already = [t for t in traces if t.status == "ALREADY_NOTIFIED"]
        new = [t for t in traces if t.status == "NOTIFIED"]
        print("\nAlready notified:")
        for t in already:
            print(f"- {t.title}")
        if not already:
            print("(none)")

        print("\nNew notifications:")
        for t in new:
            print(f"- {t.title}")
        if not new:
            print("(none)")

        breakdown = self.rejection_breakdown_for(company)
        if breakdown:
            print("\nRejected:")
            for reason, count in breakdown.items():
                print(f"- {reason}: {count}")

        print("\nExtraction confidence (job accepted):")
        for t in traces:
            if t.status in ("NOTIFIED", "ALREADY_NOTIFIED"):
                job = t.job or {}
                title_ok = "✔" if job.get("title") else "✘"
                dept_ok = "✔" if job.get("department") else "✘"
                loc_ok = "✔" if job.get("location") and job["location"].lower() != "unknown" else "✘"
                print(f"- \"{t.title}\": Title {title_ok}  Department {dept_ok}  "
                      f"Location {loc_ok}  Confidence={t.confidence}")
