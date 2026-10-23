from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    name: str
    duration: int
    deps: tuple[str, ...] = ()
    priority: int = 0


@dataclass
class Schedule:
    starts: dict[str, int]
    ends: dict[str, int]
    worker: dict[str, int]
    makespan: int


class JobError(Exception):
    pass
