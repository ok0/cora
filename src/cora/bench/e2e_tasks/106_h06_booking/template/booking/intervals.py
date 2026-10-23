from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int
    end: int


def overlaps(a: Interval, b: Interval) -> bool:
    raise NotImplementedError


def merge(items: list[Interval]) -> list[Interval]:
    raise NotImplementedError
