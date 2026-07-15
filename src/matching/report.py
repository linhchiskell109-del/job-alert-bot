"""Explainability logging cho matching engine — KHÔNG chứa logic matching/duplicate,
chỉ định dạng/tổng hợp kết quả thành bảng debug + báo cáo tổng kết cuối lần chạy.

Pipeline (xem src/main.py) tính semantic matching cho MỌI job scrape được (kể cả
job đã seen trước đó), rồi mới xác định duplicate — nên mỗi dòng trong bảng có đủ
cả kết quả matching LẪN trạng thái duplicate/notify, tách biệt rõ 2 khái niệm:

    "job này có phù hợp không" (accepted/reason)  — KHÔNG phụ thuộc duplicate
    "job này có được gửi email không" (notify)     — accepted AND KHÔNG duplicate
"""
from dataclasses import dataclass, field

from matching.engine import MatchResult

# Gộp "excluded_function" và "keyword" chung 1 nhãn "Rejected by function" —
# cả 2 đều là "không tìm thấy / bị loại ở bước function", chỉ khác lý do kỹ
# thuật (không khớp gì vs. khớp nhưng bị loại hẳn).
REASON_LABELS = {
    "accepted": "Accepted",
    "excluded_function": "Rejected by function",
    "keyword": "Rejected by function",
    "score_too_low": "Rejected by score",
    "location": "Rejected by location",
    "experience": "Rejected by experience",
}

MAX_COL = {"company": 24, "title": 42, "industry": 16, "function": 14, "level": 12}


@dataclass
class ReportRow:
    company: str
    title: str
    industry: str
    function: str
    level: str
    score: float
    duplicate: bool
    notify: bool
    reason: str  # "accepted" | "excluded_function" | "keyword" | "score_too_low" | "location" | "experience"


@dataclass
class MatchReport:
    rows: list = field(default_factory=list)

    def add(self, company: str, title: str, result: MatchResult, duplicate: bool, notify: bool):
        self.rows.append(ReportRow(
            company=company,
            title=title,
            industry=result.industry_display,
            function=result.function_display or "-",
            level=result.level_display or "-",
            score=result.score,
            duplicate=duplicate,
            notify=notify,
            reason=result.reason,
        ))

    def add_legacy(self, company: str, title: str, accepted: bool, duplicate: bool, notify: bool):
        """Dùng khi matching_engine = 'legacy' (filters.job_matches cũ) — không có
        industry/function/level/score chi tiết nên để '-'."""
        self.rows.append(ReportRow(
            company=company, title=title, industry="-", function="-", level="-",
            score=100.0 if accepted else 0.0, duplicate=duplicate, notify=notify,
            reason="accepted" if accepted else "keyword",
        ))

    @staticmethod
    def _truncate(text: str, width: int) -> str:
        text = text or ""
        return text if len(text) <= width else text[: width - 1] + "…"

    def print_table(self):
        if not self.rows:
            print("\n(Không có job nào để hiển thị debug table.)")
            return

        headers = ["Company", "Title", "Industry", "Function", "Level", "Score", "Duplicate", "Notify"]
        widths = [MAX_COL["company"], MAX_COL["title"], MAX_COL["industry"],
                  MAX_COL["function"], MAX_COL["level"], 6, 9, 6]

        def fmt_row(cells):
            return " | ".join(str(c).ljust(w) for c, w in zip(cells, widths))

        print("\n=== Debug table (tất cả job scrape được lần này) ===")
        print(fmt_row(headers))
        print("-+-".join("-" * w for w in widths))
        for r in self.rows:
            print(fmt_row([
                self._truncate(r.company, MAX_COL["company"]),
                self._truncate(r.title, MAX_COL["title"]),
                self._truncate(r.industry, MAX_COL["industry"]),
                self._truncate(r.function, MAX_COL["function"]),
                self._truncate(r.level, MAX_COL["level"]),
                f"{r.score:.0f}",
                "✅" if r.duplicate else "❌",
                "✅" if r.notify else "❌",
            ]))

    def print_summary(self):
        accepted = sum(1 for r in self.rows if r.reason == "accepted")
        notified = sum(1 for r in self.rows if r.notify)
        duplicates = sum(1 for r in self.rows if r.duplicate)
        rejected_score = sum(1 for r in self.rows if r.reason == "score_too_low")
        rejected_function = sum(1 for r in self.rows if r.reason in ("keyword", "excluded_function"))
        rejected_experience = sum(1 for r in self.rows if r.reason == "experience")
        rejected_location = sum(1 for r in self.rows if r.reason == "location")

        print("\n=== Matching summary ===")
        print(f"Accepted: {accepted}")
        print(f"Notifications sent: {notified}")
        print(f"Duplicates: {duplicates}")
        print(f"Rejected by score: {rejected_score}")
        print(f"Rejected by function: {rejected_function}")
        print(f"Rejected by experience: {rejected_experience}")
        print(f"Rejected by location: {rejected_location}")
