"""Explainability logging cho matching engine — KHÔNG chứa logic matching, chỉ
định dạng/tổng hợp MatchResult (matching/engine.py) thành log dễ đọc + báo cáo
tổng kết cuối lần chạy, đúng yêu cầu debug trong đề bài:

    Accepted: 12
    Rejected -> Duplicate: 18 | Keyword: 10 | Score too low: 14 | Location: 3 | Experience: 5
"""
from dataclasses import dataclass, field

from matching.engine import MatchResult

REASON_LABELS = {
    "accepted": "Accepted",
    "duplicate": "Duplicate",
    "excluded_function": "Keyword",       # gộp chung nhóm "Keyword" như ví dụ trong đề bài
    "keyword": "Keyword",
    "score_too_low": "Score too low",
    "location": "Location",
    "experience": "Experience",
}


@dataclass
class MatchReport:
    counts: dict = field(default_factory=dict)

    def record(self, reason: str):
        label = REASON_LABELS.get(reason, reason)
        self.counts[label] = self.counts.get(label, 0) + 1

    def record_duplicate(self):
        self.record("duplicate")

    def record_result(self, result: MatchResult):
        self.record(result.reason)

    def print_summary(self):
        accepted = self.counts.get("Accepted", 0)
        rejected_parts = [
            f"{label}: {count}"
            for label, count in self.counts.items()
            if label != "Accepted"
        ]
        print("\n=== Matching summary ===")
        print(f"Accepted: {accepted}")
        if rejected_parts:
            print("Rejected -> " + " | ".join(rejected_parts))
        else:
            print("Rejected -> (none)")


def log_job_result(company: str, job: dict, result: MatchResult):
    title = job.get("title", "")
    if result.accepted:
        print(f"  [ACCEPT] {company} — \"{title}\" -> {result.reason_detail}")
    else:
        print(f"  [REJECT] {company} — \"{title}\" -> {REASON_LABELS.get(result.reason, result.reason)}"
              f" ({result.reason_detail})")
