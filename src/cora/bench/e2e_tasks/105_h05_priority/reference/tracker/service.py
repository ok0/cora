from __future__ import annotations

from tracker import storage
from tracker.models import PRIORITIES, Task

_RANK = {"high": 0, "normal": 1, "low": 2}


class Tracker:
    def __init__(self, path: str) -> None:
        self.path = path

    def add(self, title: str, priority: str = "normal") -> Task:
        if priority not in PRIORITIES:
            raise ValueError(f"invalid priority: {priority}")
        tasks = storage.load(self.path)
        next_id = max((t.id for t in tasks), default=0) + 1
        task = Task(next_id, title, priority=priority)
        tasks.append(task)
        storage.save(self.path, tasks)
        return task

    def complete(self, task_id: int) -> None:
        tasks = storage.load(self.path)
        for t in tasks:
            if t.id == task_id:
                t.done = True
                storage.save(self.path, tasks)
                return
        raise KeyError(task_id)

    def list(self, sort: str = "id") -> list[Task]:
        tasks = storage.load(self.path)
        if sort == "id":
            return sorted(tasks, key=lambda t: t.id)
        if sort == "priority":
            return sorted(tasks, key=lambda t: (_RANK[t.priority], t.id))
        raise ValueError(f"invalid sort: {sort}")
