from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, path: Path, on_event: Callable[[dict], None] | None = None) -> None:
        self.path = path
        self.on_event = on_event
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type: str, **data: Any) -> dict:
        event = {"ts": datetime.now(UTC).isoformat(), "type": type, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.on_event is not None:
            self.on_event(event)
        return event


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
