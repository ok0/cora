from __future__ import annotations

import re

_HHMM = re.compile(r"[0-9]{2}:[0-9]{2}")


def parse_hhmm(s: str, *, end: bool = False) -> int:
    if _HHMM.fullmatch(s):
        hours, minutes = int(s[:2]), int(s[3:])
        if hours <= 23 and minutes <= 59:
            return hours * 60 + minutes
    if end and s == "24:00":
        return 1440
    raise ValueError(f"bad time: {s!r}")


def format_hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"
