"""'Dedicated parser' dùng cho các career site render qua JS (SPA) mà CHƯA xác
định được ATS/API public rõ ràng (vd BCG - Phenom People, Coca-Cola, Techcombank,
VNG) — xem pipeline.py::COMPANY_PARSER_OVERRIDES.

heuristic chung (extract_jobs_from_html) chỉ dựa vào path chứa từ khoá
job/careers -> dễ khớp nhầm nav link (path '/careers/students',
'/careers/explore' CŨNG chứa từ khoá "careers"). Ở đây thêm 1 điều kiện LỌC SAU
dựa trên URL: job THẬT hầu như LUÔN có 1 ID (số dài >=4 chữ số hoặc UUID) trong
path/query — nav link không bao giờ có. Kết hợp với validation layer (lọc theo
nội dung title) thành 2 lớp bảo vệ độc lập.

Đây KHÔNG phải parser bịa selector CSS cho từng site (vì các site này là SPA,
không quan sát được DOM thật từ môi trường không chạy JS) — là 1 bộ lọc
NGHIÊM NGẶT HƠN áp dụng thêm sau khi Playwright render xong. Khi có điều kiện
quan sát DOM thật của từng site (vd từ log lỗi production), nên thay bằng
selector chính xác hơn ngay tại đây — cấu trúc file/hàm y hệt các adapter
khác nên thay thế không ảnh hưởng phần còn lại của pipeline.
"""
import re

from scrapers import playwright_scraper

JOB_ID_PATTERN = re.compile(
    r"\d{5,}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _has_job_id(url: str) -> bool:
    return bool(JOB_ID_PATTERN.search(url))


def fetch(url: str, company: str, extra_keywords: tuple = ()) -> list[dict]:
    jobs = playwright_scraper.fetch(url, company, extra_keywords)
    return [j for j in jobs if _has_job_id(j.get("url", ""))]
