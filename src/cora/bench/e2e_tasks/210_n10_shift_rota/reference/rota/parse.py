import re

from .model import DAYS, Shift

_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _minutes(text: str) -> int | None:
    m = _CLOCK.match(text)
    if m is None:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_shift(id: str, text: str) -> Shift:
    parts = text.split()
    if len(parts) == 2 and parts[0] in DAYS and "-" in parts[1]:
        a, _, b = parts[1].partition("-")
        start, end = _minutes(a), _minutes(b)
        if start is not None and end is not None and start != end:
            return Shift(id, DAYS.index(parts[0]), start, end)
    raise ValueError(f"bad shift '{text}'")


def parse_unavailable(text: str) -> tuple[int, int, int]:
    parts = text.split()
    if len(parts) == 1 and parts[0] in DAYS:
        return (DAYS.index(parts[0]), 0, 1440)
    if len(parts) == 2 and parts[0] in DAYS and "-" in parts[1]:
        a, _, b = parts[1].partition("-")
        start, end = _minutes(a), _minutes(b)
        if start is not None and end is not None and start < end:
            return (DAYS.index(parts[0]), start, end)
    raise ValueError(f"bad unavailability '{text}'")
