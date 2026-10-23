from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("empty interval")


def overlaps(a: Interval, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def merge(items: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for item in sorted(items, key=lambda i: (i.start, i.end)):
        if out and item.start <= out[-1].end:
            last = out.pop()
            out.append(Interval(last.start, max(last.end, item.end)))
        else:
            out.append(item)
    return out
