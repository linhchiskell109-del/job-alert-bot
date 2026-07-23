"""Phân loại lỗi RIÊNG BIỆT cho Navigation Engine — KHÔNG BAO GIỜ gộp chung
thành 1 lỗi "UNREACHABLE" mơ hồ. pipeline.py bắt từng loại và ghi vào
ScrapeStatus.detail với thông điệp cụ thể, đúng loại lỗi.

Phân biệt để phục vụ retry strategy (xem engine.py::navigate):
  - Timeout / NavigationFailure : có thể là lỗi tạm thời (mạng chậm, site load
    chậm) -> ĐƯỢC retry.
  - SelectorNotFound / TargetURLMismatch : lệch cấu hình/DOM thật, retry không
    giúp gì -> KHÔNG retry.
  - ParserFailure : lỗi ở bước PARSE (sau khi navigate xong), KHÔNG phát sinh
    từ navigation engine — định nghĩa ở đây để dùng chung 1 chỗ, nhưng do
    pipeline.py raise khi bọc lệnh gọi parser, tách biệt hẳn khỏi navigation
    để không bao giờ bị retry nhầm (yêu cầu 6: "Do not retry parser failures").
"""


class NavigationFailure(Exception):
    """Lỗi navigation chung (browser crash, không rõ nguyên nhân cụ thể hơn).
    Base class cho các lỗi navigation khác — bắt NavigationFailure sẽ bắt được
    cả SelectorNotFound/Timeout/TargetURLMismatch (đều kế thừa từ đây), nhưng
    code muốn phân biệt CỤ THỂ nên bắt subclass trước."""


class SelectorNotFound(NavigationFailure):
    """1 action (click_css/click_text/click_xpath/select_option/fill/press/
    wait_selector...) không tìm thấy element sau khi đã đợi hết thời gian cho
    phép — DOM thực tế không khớp config, KHÔNG phải lỗi tạm thời."""


class Timeout(NavigationFailure):
    """Vượt quá thời gian chờ cho 1 action hoặc điều hướng trang (page load,
    networkidle...) — CÓ THỂ là lỗi tạm thời (mạng chậm/site chậm)."""


class TargetURLMismatch(NavigationFailure):
    """Navigation chạy xong (không lỗi action nào) nhưng URL cuối cùng KHÔNG
    khớp `target_url` cấu hình — cảnh báo rõ ràng thay vì âm thầm dùng nhầm
    URL, vì có thể site đã đổi cấu trúc.

    Mang theo `final_url` (URL THỰC TẾ điều hướng tới) — caller (pipeline.py)
    có thể chọn vẫn dùng URL này (đáng tin hơn config có thể đã cũ) thay vì
    coi lỗi này là fatal tuyệt đối."""

    def __init__(self, message: str, final_url: str = None):
        super().__init__(message)
        self.final_url = final_url


class ParserFailure(Exception):
    """Lỗi ở bước PARSE (SAU KHI navigation đã thành công) — KHÔNG kế thừa
    NavigationFailure vì đây là lỗi khác loại hoàn toàn (parser đọc HTML/JSON
    lỗi, không phải lỗi điều hướng trình duyệt). Định nghĩa ở đây để
    pipeline.py dùng thống nhất, tách biệt rõ khỏi navigation errors."""
