"""Text helpers."""


def slugify(value: str) -> str:
    """Return a URL slug: lower-case letters and digits separated by single dashes."""
    out = []
    for ch in value.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")
