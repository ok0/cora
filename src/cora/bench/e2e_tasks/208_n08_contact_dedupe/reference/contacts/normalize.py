GMAIL_DOMAINS = ("gmail.com", "googlemail.com")


def normalize_email(s: str) -> str:
    value = s.strip().lower()
    if "@" not in value:
        return value
    local, _, domain = value.partition("@")
    if domain in GMAIL_DOMAINS:
        local = local.replace(".", "").split("+", 1)[0]
        return f"{local}@gmail.com"
    return f"{local}@{domain}"


def normalize_phone(s: str) -> str:
    text = s.strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if text.startswith("00"):
        return "+" + digits[2:]
    if len(digits) == 10:
        return "+1" + digits
    if digits:
        return "+" + digits
    return ""
