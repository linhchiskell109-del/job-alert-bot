"""Chuẩn hoá text dùng chung cho filters.py và state.py — 1 nơi duy nhất định nghĩa
thế nào là 'cùng 1 chuỗi' (bỏ dấu, lowercase, chuẩn hoá khoảng trắng)."""
import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt. Dùng cho so khớp keyword (contains)."""
    text = (text or "").lower().strip()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_key(text: str) -> str:
    """normalize() + thay mọi ký tự không phải chữ/số bằng space.
    Dùng để tạo hash key ổn định (không lệch vì dấu câu, khoảng trắng thừa...)."""
    text = normalize(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
