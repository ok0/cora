from __future__ import annotations

from .intervals import Interval, merge, overlaps
from .timeparse import format_hhmm, parse_hhmm


class Schedule:
    def __init__(self) -> None:
        self._rooms: dict[str, list[Interval]] = {}

    def book(self, room: str, start: str, end: str) -> bool:
        s = parse_hhmm(start)
        e = parse_hhmm(end, end=True)
        if e < s:
            parts = [Interval(s, 1440)]
            if e > 0:
                parts.append(Interval(0, e))
        else:
            parts = [Interval(s, e)]
        booked = self._rooms.setdefault(room, [])
        for part in parts:
            if any(overlaps(part, other) for other in booked):
                return False
        booked.extend(parts)
        return True

    def free_slots(self, room: str, day_start: str, day_end: str, min_len: int) -> list[tuple[str, str]]:
        lo = parse_hhmm(day_start)
        hi = parse_hhmm(day_end, end=True)
        cursor = lo
        gaps: list[tuple[int, int]] = []
        for busy in merge(self._rooms.get(room, [])):
            if busy.end <= cursor:
                continue
            if busy.start >= hi:
                break
            if busy.start > cursor:
                gaps.append((cursor, busy.start))
            cursor = max(cursor, busy.end)
            if cursor >= hi:
                break
        if cursor < hi:
            gaps.append((cursor, hi))
        return [
            (format_hhmm(a), format_hhmm(b))
            for a, b in gaps
            if b - a >= min_len
        ]
