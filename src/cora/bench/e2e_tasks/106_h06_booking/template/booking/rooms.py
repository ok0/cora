from __future__ import annotations

from .intervals import Interval


class Schedule:
    def __init__(self) -> None:
        self._rooms: dict[str, list[Interval]] = {}

    def book(self, room: str, start: str, end: str) -> bool:
        raise NotImplementedError

    def free_slots(self, room: str, day_start: str, day_end: str, min_len: int) -> list[tuple[str, str]]:
        raise NotImplementedError
