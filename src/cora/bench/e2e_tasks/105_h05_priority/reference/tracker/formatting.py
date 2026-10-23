from __future__ import annotations

from tracker.models import Task

_MARKER = {"high": "H", "normal": "N", "low": "L"}


def render(tasks: list[Task]) -> str:
    return "\n".join(
        f"{t.id:>3} [{_MARKER[t.priority]}] [{'x' if t.done else ' '}] {t.title}" for t in tasks
    )
