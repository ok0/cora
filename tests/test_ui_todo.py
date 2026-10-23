from __future__ import annotations

from cora.cli.ui.theme import ASCII_GLYPHS, THEMES, UNICODE_GLYPHS
from cora.cli.ui.todoview import todo_text
from cora.core.tools.base import TodoItem


def test_todo_text_unicode() -> None:
    items = [TodoItem("a", "pending"), TodoItem("b", "in_progress"), TodoItem("c", "completed")]
    text = todo_text(items, THEMES["default"], UNICODE_GLYPHS)
    assert text.plain == "  ☐ a\n  ◐ b\n  ☒ c"


def test_todo_text_ascii() -> None:
    items = [TodoItem("a", "pending"), TodoItem("b", "in_progress"), TodoItem("c", "completed")]
    text = todo_text(items, THEMES["default"], ASCII_GLYPHS)
    assert text.plain == "  [ ] a\n  [~] b\n  [x] c"


def test_todo_text_empty() -> None:
    assert todo_text([], THEMES["default"], UNICODE_GLYPHS).plain == "  (no TODO items)"
