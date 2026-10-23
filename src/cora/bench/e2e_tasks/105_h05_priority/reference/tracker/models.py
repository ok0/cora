from __future__ import annotations

from dataclasses import dataclass

PRIORITIES = ("low", "normal", "high")


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: str = "normal"

    def __post_init__(self) -> None:
        if self.priority not in PRIORITIES:
            raise ValueError(f"invalid priority: {self.priority}")
