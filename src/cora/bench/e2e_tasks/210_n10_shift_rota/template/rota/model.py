from dataclasses import dataclass

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class Shift:
    id: str
    day: int
    start: int
    end: int


@dataclass(frozen=True)
class Staff:
    name: str
    max_hours: int
    unavailable: tuple[str, ...] = ()


@dataclass
class Rota:
    shifts: list[Shift]
    assignments: dict[str, str | None]
    minutes: dict[str, int]
