from __future__ import annotations


def parse_hhmm(s: str, *, end: bool = False) -> int:
    raise NotImplementedError


def format_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"
