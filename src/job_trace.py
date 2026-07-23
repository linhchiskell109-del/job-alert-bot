"""Mọi job crawl được đều phải có ĐÚNG 1 trạng thái cuối cùng (terminal status)
— không job nào được "biến mất" khỏi pipeline mà không có lý do tường minh.

Luồng trạng thái:

    CRAWLED -> NORMALIZED -> (đang xử lý)
                                 |
                                 +-> REJECTED_VALIDATION  (nav/menu page, thiếu field)
                                 +-> REJECTED_LOCATION    (rõ ràng không phải VN/SEA)
                                 +-> REJECTED_FUNCTION    (không khớp function nào liên quan)
                                 +-> REJECTED_EXPERIENCE  (level không phù hợp, vd senior/manager)
                                 +-> REJECTED_SCORE       (có match nhưng điểm dưới ngưỡng)
                                 +-> ALREADY_NOTIFIED     (khớp tiêu chí NHƯNG đã báo trước đó)
                                 +-> NOTIFIED             (khớp tiêu chí VÀ là job mới)

`job` trên mỗi JobTrace LUÔN là dict đã normalize (kể cả khi trace bị reject) —
để công ty/brand vẫn phân loại được (vd shared portal) và diagnostics vẫn tính
được extraction confidence, dù job đó cuối cùng bị loại ở bước nào.
"""
from dataclasses import dataclass, field

TERMINAL_STATUSES = (
    "NOTIFIED",
    "ALREADY_NOTIFIED",
    "REJECTED_VALIDATION",
    "REJECTED_LOCATION",
    "REJECTED_FUNCTION",
    "REJECTED_EXPERIENCE",
    "REJECTED_SCORE",
)

# Nhóm "loại vì matching" — dùng để tính company-level diagnostics/rejection breakdown
REJECTED_BY_MATCHING = ("REJECTED_FUNCTION", "REJECTED_EXPERIENCE", "REJECTED_SCORE")

# reason code từ matching/engine.py -> terminal status tương ứng
_MATCH_REASON_TO_STATUS = {
    "excluded_function": "REJECTED_FUNCTION",
    "keyword": "REJECTED_FUNCTION",
    "experience": "REJECTED_EXPERIENCE",
    "score_too_low": "REJECTED_SCORE",
    "location": "REJECTED_LOCATION",  # phòng hờ — bình thường đã bị loại sớm ở pipeline rồi
}


def match_reason_to_status(reason: str) -> str:
    return _MATCH_REASON_TO_STATUS.get(reason, "REJECTED_FUNCTION")


@dataclass
class JobTrace:
    company: str
    title: str
    url: str = ""
    job: dict = None  # dict đã normalize (LUÔN có, kể cả khi bị reject)
    status: str = "CRAWLED"
    detail: str = ""
    industry: str = ""
    function: str = ""
    level: str = ""
    score: float = 0.0
    confidence: float = 1.0
    history: list = field(default_factory=list)

    def __post_init__(self):
        self.history.append(self.status)

    def set_status(self, status: str, detail: str = ""):
        self.status = status
        self.detail = detail
        self.history.append(status)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def location(self) -> str:
        return (self.job or {}).get("location", "") if self.job else ""


def extraction_confidence(job: dict) -> float:
    """Ước lượng độ tin cậy của việc trích xuất field cho 1 job — dùng để phát
    hiện parser yếu (vd luôn ra location="Unknown"). Field nào có giá trị THẬT
    (khác rỗng/"Unknown") được tính điểm theo trọng số; tổng = 1.0 nếu mọi field
    đều trích được. KHÔNG dùng field nào không tồn tại trong job (vd không phạt
    department nếu company đó vốn không có khái niệm department)."""
    weights = {"title": 0.4, "location": 0.35, "department": 0.15, "employment_type": 0.10}
    total = 0.0
    earned = 0.0
    for field_name, weight in weights.items():
        total += weight
        value = str((job or {}).get(field_name, "") or "").strip()
        if value and value.lower() != "unknown":
            earned += weight
    return round(earned / total, 2) if total else 0.0
