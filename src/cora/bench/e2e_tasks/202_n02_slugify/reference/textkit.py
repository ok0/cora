import re
import unicodedata


def word_count(text: str) -> int:
    return len(text.split())


def title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


def slugify(text: str, max_length: int | None = None) -> str:
    """Return a lowercase ASCII slug of text, cut to max_length if given."""
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be >= 1")
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if max_length is not None and len(slug) > max_length:
        cut = slug[:max_length]
        if slug[max_length] != "-" and "-" in cut:
            cut = cut[: cut.rindex("-")]
        slug = cut.rstrip("-")
    return slug
