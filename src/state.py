"""Quản lý state (job đã thấy) để không báo trùng job cũ.

Hash job KHÔNG chỉ dựa vào URL — nhiều trang thêm query string/tracking param/ID
thay đổi theo thời gian dù vẫn là cùng 1 job posting, hoặc đổi domain khi migrate
ATS. Thay vào đó hash dựa trên (company + title + location) đã chuẩn hoá (bỏ dấu,
lowercase, bỏ ký tự đặc biệt) — ổn định hơn nhiều qua thời gian.

Đánh đổi: nếu 1 công ty post 2 job cùng title + cùng location trong 2 đợt khác
nhau, đợt thứ 2 sẽ bị coi là trùng (không báo lại). Đây là giới hạn được chấp nhận
để đổi lấy việc không bị báo trùng liên tục vì URL đổi.

AUDIT (xem thêm MIGRATION.md phần "Audit duplicate detection"): khi location =
"Unknown" (không trích được — xem normalize.py), (company, title) KHÔNG ĐỦ để
phân biệt 2 job KHÁC NHAU cùng title (vd 2 đợt tuyển "Warehouse Coordinator"
khác nhau, cùng công ty, cả 2 đều không trích được location) — sẽ bị coi là
CÙNG 1 job, job thứ 2 bị nuốt mất, không bao giờ được báo. Để giảm rủi ro này
mà KHÔNG quay lại vấn đề gốc (URL đổi -> báo trùng liên tục), chỉ thêm URL PATH
(không kèm query string/tracking param) làm tín hiệu phụ, và CHỈ khi location
không đáng tin (Unknown/trống) — trường hợp location trích được bình thường thì
hash không đổi so với trước (không ảnh hưởng job đã có trong state.json cũ)."""
import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from textnorm import normalize_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "state.json")


def job_hash(job: dict) -> str:
    location_norm = normalize_key(job.get("location", ""))
    parts = [
        normalize_key(job.get("company", "")),
        normalize_key(job.get("title", "")),
        location_norm,
    ]
    if location_norm in ("", "unknown"):
        # location không đáng tin để phân biệt job -> thêm URL PATH (bỏ query
        # string, vốn hay đổi theo tracking param) làm tín hiệu phụ, tránh 2 job
        # THẬT SỰ KHÁC NHAU (cùng title, cùng company, cả 2 đều không rõ
        # location) bị coi là 1.
        url_path = urlsplit(job.get("url", "") or "").path.rstrip("/")
        parts.append(normalize_key(url_path))
    key = "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def load_state(path: str = STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {"seen": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("seen", {})
    return data


def save_state(state: dict, path: str = STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_new(state: dict, job: dict) -> bool:
    return job_hash(job) not in state["seen"]


def mark_seen(state: dict, job: dict):
    h = job_hash(job)
    state["seen"][h] = {
        "url": job.get("url", ""),
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "first_seen": datetime.now(timezone.utc).isoformat(),
    }
