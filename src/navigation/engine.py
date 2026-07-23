"""Navigation Engine — thực thi 1 dãy action (config-driven) trên 1 trang
Playwright để đi từ entry_url tới URL/trang job listing thật, rồi bàn giao lại
cho pipeline hiện có (KHÔNG đụng vào parser nào).

Thiết kế "future-proof" theo yêu cầu: navigate() trả về NavigationResult chứa
final_url (dùng ngay cho parser hiện tại, đều nhận URL string) VÀ tuỳ chọn giữ
lại page/browser_context/browser SỐNG (keep_session=True) để sau này viết
parser mới có thể tái sử dụng session đã đăng nhập/có cookie mà không cần
navigate lại từ đầu. Mặc định (keep_session=False) đóng browser ngay sau khi
lấy final_url — tránh rò rỉ tiến trình browser khi không ai cần session đó.

KHÔNG có `if company == ...` ở đâu trong file này — mọi hành vi riêng cho 1
công ty nằm hết trong config (danh sách step, target_url, retry override).
"""
import time
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright

from navigation.actions import ACTIONS
from navigation.errors import NavigationFailure, ParserFailure, SelectorNotFound, TargetURLMismatch, Timeout

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobAlertBot/2.0"
)

DEFAULT_RETRIES = 2  # số lần thử LẠI (không tính lần đầu) cho lỗi transient
RETRYABLE_ERRORS = (Timeout, NavigationFailure)  # SelectorNotFound/TargetURLMismatch là subclass NavigationFailure
                                                   # nên liệt kê tường minh loại KHÔNG retry bên dưới thay vì dựa isinstance ở đây
NON_RETRYABLE_ERRORS = (SelectorNotFound, TargetURLMismatch)


@dataclass
class NavigationResult:
    final_url: str
    logs: list = field(default_factory=list)
    page: object = None              # None trừ khi keep_session=True
    browser_context: object = None   # None trừ khi keep_session=True
    browser: object = None           # None trừ khi keep_session=True

    def close(self):
        """Gọi khi dùng xong session giữ lại (keep_session=True) — parser tương
        lai dùng xong phải tự đóng, Navigation Engine không tự đóng hộ vì
        không biết khi nào caller dùng xong."""
        for obj in (self.page, self.browser_context, self.browser):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass


def _normalize_step(raw_step) -> tuple:
    """1 step trong config là dict 1-key: {action_name: params}. `params` có
    thể là scalar (shorthand cho tham số chính) hoặc dict (đầy đủ). Trả về
    (action_name, params_dict) đã chuẩn hoá — action nào nhận shorthand gì do
    chính action function đó quy định qua bảng dưới."""
    if not isinstance(raw_step, dict) or len(raw_step) != 1:
        raise NavigationFailure(f"Navigation step không hợp lệ (phải là dict 1 key): {raw_step!r}")
    action_name, raw_params = next(iter(raw_step.items()))
    if action_name not in ACTIONS:
        raise NavigationFailure(f"Không nhận diện được action '{action_name}' — các action hỗ trợ: {sorted(ACTIONS)}")

    if raw_params is None:
        params = {}
    elif isinstance(raw_params, dict):
        params = dict(raw_params)
    else:
        # shorthand scalar -> tham số chính của từng action
        shorthand_key = {
            "click_text": "text", "click_role": "name", "click_css": "selector",
            "click_xpath": "selector", "click_icon": "name", "fill": "value",
            "wait_selector": "selector", "wait_timeout": "ms",
        }.get(action_name)
        if shorthand_key is None:
            raise NavigationFailure(
                f"Action '{action_name}' cần khai báo dạng dict đầy đủ trong config "
                f"(không hỗ trợ shorthand 1 giá trị) — nhận được: {raw_params!r}"
            )
        params = {shorthand_key: raw_params}

    return action_name, params


def _describe_step(action_name: str, params: dict) -> str:
    if action_name == "click_text":
        return f'click_text("{params.get("text")}")'
    if action_name == "click_role":
        return f'click_role(role="{params.get("role")}", name="{params.get("name")}")'
    if action_name == "click_css":
        return f'click_css("{params.get("selector")}")'
    if action_name == "click_xpath":
        return f'click_xpath("{params.get("selector")}")'
    if action_name == "click_icon":
        return f'click_icon("{params.get("name")}")'
    if action_name == "select_option":
        return f'select_option(selector="{params.get("selector")}", value="{params.get("value")}")'
    if action_name == "fill":
        return f'fill(selector="{params.get("selector")}", value="{params.get("value")}")'
    if action_name == "press":
        return f'press(selector="{params.get("selector")}", key="{params.get("key")}")'
    if action_name == "wait_selector":
        return f'wait_selector("{params.get("selector")}")'
    if action_name == "wait_networkidle":
        return "wait_networkidle()"
    if action_name == "wait_timeout":
        return f'wait_timeout({params.get("ms", 1000)}ms)'
    return f"{action_name}({params})"


def _run_steps_once(entry_url: str, steps: list, target_url: str, keep_session: bool,
                     page_timeout_ms: int, log: list) -> NavigationResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()
        try:
            log.append("[Navigation]")
            page.goto(entry_url, timeout=page_timeout_ms, wait_until="domcontentloaded")

            total = len(steps)
            for i, raw_step in enumerate(steps, start=1):
                action_name, params = _normalize_step(raw_step)
                description = _describe_step(action_name, params)
                log.append(f"\nStep {i}/{total}")
                log.append(description)
                print(f"[Navigation] Step {i}/{total}: {description}")
                try:
                    ACTIONS[action_name](page, params)
                except NavigationFailure as e:
                    log.append(f"✗ Failed: {e}")
                    print(f"[Navigation] ✗ Failed: {e}")
                    raise
                log.append("✓ Success")
                print(f"[Navigation] ✓ Success")

            final_url = page.url
            log.append(f"\nFinal URL:\n{final_url}")
            print(f"[Navigation] Final URL: {final_url}")

            if target_url and final_url.rstrip("/") != target_url.rstrip("/"):
                msg = f"URL cuối cùng ({final_url}) không khớp target_url cấu hình ({target_url})"
                log.append(f"⚠ TargetURLMismatch: {msg}")
                print(f"[Navigation] ⚠ TargetURLMismatch: {msg}")
                if not keep_session:
                    context.close()
                    browser.close()
                # Vẫn coi final_url THỰC TẾ là kết quả điều hướng (đáng tin hơn config
                # có thể đã cũ) — nhưng raise để pipeline.py BIẾT và log cảnh báo rõ,
                # tự quyết định có dùng tiếp hay không thay vì âm thầm lệch.
                raise TargetURLMismatch(msg, final_url=final_url)

            if keep_session:
                return NavigationResult(final_url=final_url, logs=log, page=page,
                                         browser_context=context, browser=browser)
            context.close()
            browser.close()
            return NavigationResult(final_url=final_url, logs=log)
        except NavigationFailure:
            if not keep_session:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
            raise
        except Exception as e:
            log.append(f"✗ Failed: lỗi không xác định ({e})")
            print(f"[Navigation] ✗ Failed: lỗi không xác định ({e})")
            if not keep_session:
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
            raise NavigationFailure(f"Lỗi navigation không xác định: {e}") from e


def navigate(entry_url: str, steps: list, target_url: str = None, keep_session: bool = False,
             retries: int = DEFAULT_RETRIES, page_timeout_ms: int = 30000) -> NavigationResult:
    """Chạy dãy `steps` tuần tự từ `entry_url`, trả về NavigationResult.

    Retry CHỈ áp dụng cho lỗi transient (Timeout/NavigationFailure chung) —
    SelectorNotFound và TargetURLMismatch KHÔNG được retry (retry không sửa
    được config/DOM lệch). Mỗi lần retry chạy lại TOÀN BỘ dãy step từ đầu với
    1 browser/page mới (không retry từng step riêng lẻ, tránh để trang ở trạng
    thái nửa vời)."""
    attempt = 0
    last_error = None
    while attempt <= retries:
        log = []
        try:
            return _run_steps_once(entry_url, steps, target_url, keep_session, page_timeout_ms, log)
        except NON_RETRYABLE_ERRORS:
            raise
        except NavigationFailure as e:
            last_error = e
            attempt += 1
            if attempt > retries:
                break
            wait_s = 1.5 * attempt
            print(f"[Navigation] Lỗi transient ({e}) — thử lại lần {attempt}/{retries} sau {wait_s}s")
            time.sleep(wait_s)

    raise last_error
