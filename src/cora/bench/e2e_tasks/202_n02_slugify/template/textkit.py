def word_count(text: str) -> int:
    return len(text.split())


def title_case(text: str) -> str:
    return " ".join(w.capitalize() for w in text.split())


def slugify(text: str, max_length: int | None = None) -> str:
    """Return a lowercase ASCII slug of text, cut to max_length if given."""
    raise NotImplementedError
