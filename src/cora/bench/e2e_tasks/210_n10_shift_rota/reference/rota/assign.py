from .model import Rota, Shift, Staff
from .rules import can_take, duration


def assign(shifts: list[Shift], staff: list[Staff]) -> Rota:
    ordered = sorted(shifts, key=lambda s: (s.day, s.start, s.id))
    held: dict[str, list[Shift]] = {p.name: [] for p in staff}
    minutes: dict[str, int] = {p.name: 0 for p in staff}
    assignments: dict[str, str | None] = {}
    for shift in ordered:
        free = [p for p in staff if can_take(p, shift, held[p.name]) is None]
        if not free:
            assignments[shift.id] = None
            continue
        pick = min(free, key=lambda p: (minutes[p.name], p.name))
        assignments[shift.id] = pick.name
        held[pick.name].append(shift)
        minutes[pick.name] += duration(shift)
    return Rota(shifts=ordered, assignments=assignments, minutes=minutes)
