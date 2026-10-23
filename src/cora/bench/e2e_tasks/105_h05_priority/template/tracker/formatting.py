from __future__ import annotations


def render(tasks: list) -> str:
    return "\n".join(f"{t.id:>3} [{'x' if t.done else ' '}] {t.title}" for t in tasks)
