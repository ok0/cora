from __future__ import annotations

from tracker import storage
from tracker.models import Task


class Tracker:
    def __init__(self, path: str) -> None:
        self.path = path

    def add(self, title: str) -> Task:
        tasks = storage.load(self.path)
        next_id = max((t.id for t in tasks), default=0) + 1
        task = Task(next_id, title)
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

    def list(self) -> list[Task]:
        return sorted(storage.load(self.path), key=lambda t: t.id)
