from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text

from cora.cli.ui.theme import Glyphs, Theme
from cora.core.tools.base import TodoItem


def todo_text(items: Sequence[TodoItem], theme: Theme, glyphs: Glyphs) -> Text:
    if not items:
        return Text("  (no TODO items)", style=theme.dim)
    marks = {
        "pending": (glyphs.todo_pending, theme.todo_pending),
        "in_progress": (glyphs.todo_active, theme.todo_active),
        "completed": (glyphs.todo_done, theme.todo_done),
    }
    text = Text()
    for i, item in enumerate(items):
        if i:
            text.append("\n")
        mark, style = marks[item.status]
        text.append(f"  {mark} {item.content}", style=style or None)
    return text
