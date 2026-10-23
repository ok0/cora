"""Duplicate detection and merging of contact rows."""


def dedupe(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """Merge duplicate rows and return (kept_rows, removed_count)."""
    raise NotImplementedError
