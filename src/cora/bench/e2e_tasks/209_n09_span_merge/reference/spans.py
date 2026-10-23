def covered(spans: list[tuple[int, int]], x: int) -> bool:
    return any(s <= x < e for s, e in spans)


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    for s, e in spans:
        if s > e:
            raise ValueError(f"bad span ({s}, {e})")
    out: list[tuple[int, int]] = []
    for s, e in sorted((s, e) for s, e in spans if s < e):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out
