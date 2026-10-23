from .model import Shift, Staff
from .parse import parse_unavailable

REST_MINUTES = 660


def interval(shift: Shift) -> tuple[int, int]:
    start = shift.day * 1440 + shift.start
    return start, start + (shift.end - shift.start) % 1440


def duration(shift: Shift) -> int:
    return (shift.end - shift.start) % 1440


def can_take(staff: Staff, shift: Shift, assigned: list[Shift]) -> str | None:
    start, end = interval(shift)
    for text in staff.unavailable:
        day, w_start, w_end = parse_unavailable(text)
        if w_start == 0 and w_end == 1440:
            if shift.day == day:
                return "unavailable"
        elif start < day * 1440 + w_end and day * 1440 + w_start < end:
            return "unavailable"
    for other in assigned:
        o_start, o_end = interval(other)
        if start < o_end and o_start < end:
            return "overlap"
    for other in assigned:
        o_start, o_end = interval(other)
        if max(o_start - end, start - o_end) < REST_MINUTES:
            return "rest"
    if sum(duration(o) for o in assigned) + duration(shift) > staff.max_hours * 60:
        return "hours"
    return None
