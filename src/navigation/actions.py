"""1 hàm cho MỖI loại action — nhận (page, params) đã chuẩn hoá từ config, gọi
Playwright thuần, KHÔNG có logic riêng cho công ty nào. engine.py dispatch tới
đây theo tên action trong config, không hardcode `if company == ...` ở đâu cả.

Phân biệt SelectorNotFound vs Timeout (xem errors.py):
  1. Check TỒN TẠI trước (wait_for_selector state="attached", timeout ngắn) —
     không thấy trong DOM => SelectorNotFound (config/DOM lệch, retry vô ích).
  2. Nếu tồn tại, mới thực hiện action (click/fill/...) với timeout riêng —
     action không hoàn tất kịp (bị che, đang loading...) => Timeout (có thể
     tạm thời, retry có ý nghĩa).

Mỗi action nhận `params` đã ở dạng dict (engine.py lo việc chuẩn hoá shorthand
scalar -> dict trước khi gọi vào đây).
"""
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from navigation.errors import SelectorNotFound, Timeout

DEFAULT_EXIST_TIMEOUT_MS = 8000
DEFAULT_ACTION_TIMEOUT_MS = 15000


def _timeouts(params: dict) -> tuple:
    exist_ms = params.get("exist_timeout_ms", DEFAULT_EXIST_TIMEOUT_MS)
    action_ms = params.get("timeout_ms", DEFAULT_ACTION_TIMEOUT_MS)
    return exist_ms, action_ms


def _assert_exists(page, selector: str, exist_ms: int, description: str):
    try:
        page.wait_for_selector(selector, state="attached", timeout=exist_ms)
    except PlaywrightTimeoutError as e:
        raise SelectorNotFound(f"{description}: không tìm thấy element trong DOM sau {exist_ms}ms "
                                f"(selector/text: {selector!r})") from e


def _run_action(fn, description: str):
    try:
        fn()
    except PlaywrightTimeoutError as e:
        raise Timeout(f"{description}: hết thời gian chờ khi thực hiện action") from e


def click_text(page, params: dict):
    text = params.get("text")
    exact = bool(params.get("exact", False))
    exist_ms, action_ms = _timeouts(params)
    locator = page.get_by_text(text, exact=exact).first
    if not _locator_visible_soon(locator, exist_ms):
        raise SelectorNotFound(f"click_text({text!r}): không tìm thấy element có text khớp trong DOM sau {exist_ms}ms")
    _run_action(lambda: locator.click(timeout=action_ms), f"click_text({text!r})")


def _locator_visible_soon(locator, timeout_ms: int) -> bool:
    """Trả về True nếu locator xuất hiện trong `timeout_ms` — dùng cho các
    action dựa trên Locator (get_by_text/get_by_role/get_by_label) vốn không
    nhận CSS selector string để đưa thẳng vào wait_for_selector()."""
    try:
        locator.wait_for(state="attached", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def click_role(page, params: dict):
    role = params.get("role")
    name = params.get("name")
    exist_ms, action_ms = _timeouts(params)
    locator = page.get_by_role(role, name=name).first
    if not _locator_visible_soon(locator, exist_ms):
        raise SelectorNotFound(f"click_role(role={role!r}, name={name!r}): không tìm thấy element trong DOM sau {exist_ms}ms")
    _run_action(lambda: locator.click(timeout=action_ms), f"click_role(role={role!r}, name={name!r})")


def click_css(page, params: dict):
    selector = params.get("selector")
    exist_ms, action_ms = _timeouts(params)
    _assert_exists(page, selector, exist_ms, f"click_css({selector!r})")
    _run_action(lambda: page.locator(selector).first.click(timeout=action_ms), f"click_css({selector!r})")


def click_xpath(page, params: dict):
    selector = params.get("selector")
    xpath_selector = f"xpath={selector}"
    exist_ms, action_ms = _timeouts(params)
    _assert_exists(page, xpath_selector, exist_ms, f"click_xpath({selector!r})")
    _run_action(lambda: page.locator(xpath_selector).first.click(timeout=action_ms), f"click_xpath({selector!r})")


def click_icon(page, params: dict):
    """Icon thường không có text hiển thị — thử qua accessible name (aria-label
    /title, Playwright get_by_label) thay vì đoán class CSS riêng cho icon
    library nào đó."""
    name = params.get("name")
    exist_ms, action_ms = _timeouts(params)
    locator = page.get_by_label(name).first
    if not _locator_visible_soon(locator, exist_ms):
        raise SelectorNotFound(f"click_icon({name!r}): không tìm thấy element có aria-label/title khớp trong DOM sau {exist_ms}ms")
    _run_action(lambda: locator.click(timeout=action_ms), f"click_icon({name!r})")


def select_option(page, params: dict):
    selector = params.get("selector")
    value = params.get("value")
    if not selector:
        raise SelectorNotFound(
            f"select_option(value={value!r}): thiếu 'selector' trong config — Navigation Engine "
            f"KHÔNG tự đoán selector dropdown, cần khai báo rõ trong config.yaml trước khi công ty "
            f"này có thể dùng strategy điều hướng tự động."
        )
    exist_ms, action_ms = _timeouts(params)
    _assert_exists(page, selector, exist_ms, f"select_option({selector!r}, {value!r})")
    _run_action(lambda: page.locator(selector).first.select_option(label=value, timeout=action_ms),
                f"select_option({selector!r}, {value!r})")


def fill(page, params: dict):
    selector = params.get("selector")
    value = params.get("value", "")
    exist_ms, action_ms = _timeouts(params)
    _assert_exists(page, selector, exist_ms, f"fill({selector!r})")
    _run_action(lambda: page.locator(selector).first.fill(value, timeout=action_ms), f"fill({selector!r}, {value!r})")


def press(page, params: dict):
    selector = params.get("selector")
    key = params.get("key")
    exist_ms, action_ms = _timeouts(params)
    if selector:
        _assert_exists(page, selector, exist_ms, f"press({selector!r}, {key!r})")
        _run_action(lambda: page.locator(selector).first.press(key, timeout=action_ms), f"press({selector!r}, {key!r})")
    else:
        _run_action(lambda: page.keyboard.press(key), f"press(page-level, {key!r})")


def wait_selector(page, params: dict):
    selector = params.get("selector")
    state = params.get("state", "visible")
    _, action_ms = _timeouts(params)
    try:
        page.wait_for_selector(selector, state=state, timeout=action_ms)
    except PlaywrightTimeoutError as e:
        raise SelectorNotFound(f"wait_selector({selector!r}, state={state!r}): không xuất hiện sau {action_ms}ms") from e


def wait_networkidle(page, params: dict):
    _, action_ms = _timeouts(params)
    try:
        page.wait_for_load_state("networkidle", timeout=action_ms)
    except PlaywrightTimeoutError as e:
        raise Timeout(f"wait_networkidle(): trang chưa idle sau {action_ms}ms") from e


def wait_timeout(page, params: dict):
    ms = params.get("ms", 1000)
    page.wait_for_timeout(ms)


ACTIONS = {
    "click_text": click_text,
    "click_role": click_role,
    "click_css": click_css,
    "click_xpath": click_xpath,
    "click_icon": click_icon,
    "select_option": select_option,
    "fill": fill,
    "press": press,
    "wait_selector": wait_selector,
    "wait_networkidle": wait_networkidle,
    "wait_timeout": wait_timeout,
}
