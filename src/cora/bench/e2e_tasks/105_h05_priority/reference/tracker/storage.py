from __future__ import annotations

import json
from pathlib import Path

from tracker.models import Task


def load(path: str) -> list[Task]:
    file = Path(path)
    if not file.exists():
        return []
    tasks = []
    for line in file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        tasks.append(Task(
            id=record["id"],
            title=record["title"],
            done=record["done"],
            priority=record.get("priority", "normal"),
        ))
    return tasks


def save(path: str, tasks: list[Task]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for t in tasks:
            record = {"id": t.id, "title": t.title, "done": t.done, "priority": t.priority}
            f.write(json.dumps(record) + "\n")
