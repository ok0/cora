def covered(spans: list[tuple[int, int]], x: int) -> bool:
    return any(s <= x < e for s, e in spans)


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return the sorted, merged spans.

    Raise ValueError(f"bad span ({s}, {e})") if any span has s > e.
    """
    raise NotImplementedError
