from .model import DAYS, Rota


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_csv(rota: Rota) -> str:
    lines = ["shift,day,start,end,staff"]
    for shift in rota.shifts:
        staff = rota.assignments[shift.id] or ""
        lines.append(
            f"{shift.id},{DAYS[shift.day]},{_clock(shift.start)},{_clock(shift.end)},{staff}"
        )
    return "\n".join(lines) + "\n"


def summary(rota: Rota) -> str:
    lines = [f"{name}: {minutes / 60:.1f}h" for name, minutes in sorted(rota.minutes.items())]
    unfilled = [shift.id for shift in rota.shifts if rota.assignments[shift.id] is None]
    lines.append("unfilled: " + (", ".join(unfilled) if unfilled else "none"))
    return "\n".join(lines) + "\n"
