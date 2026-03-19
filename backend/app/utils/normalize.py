import re


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[-10:]
    return digits


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())