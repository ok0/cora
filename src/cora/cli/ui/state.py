from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from cora.cli.ui.theme import ASCII_GLYPHS, THEMES, UNICODE_GLYPHS, Glyphs, Theme
from cora.core.config import CYCLE_APPROVAL_MODES, UiSettings
from cora.core.tools.base import TodoItem


@dataclass
class UiState:
    theme: Theme
    color_mode: str = "auto"
    ascii: bool = False
    approval: str = "ask"
    model: str | None = None
    groups: tuple[str, ...] = ()
    plan: bool = False
    check: bool = False
    delegate: bool = False
    cost_usd: float | None = None
    context_pct: float | None = None
    started: float = field(default_factory=time.monotonic)
    show_todos: bool = True
    last_collapsed: str | None = None
    on_cycle_approval: Callable[[], str] | None = None
    on_toggle_todos: Callable[[], str] | None = None
    get_todos: Callable[[], Sequence[TodoItem]] | None = None
    mouse: bool | None = None
    unseen: bool = False

    @classmethod
    def from_settings(cls, s: UiSettings) -> UiState:
        return cls(theme=THEMES[s.theme], color_mode=s.color, ascii=s.ascii)

    @property
    def glyphs(self) -> Glyphs:
        return ASCII_GLYPHS if self.ascii else UNICODE_GLYPHS


def next_approval(mode: str) -> str:
    if mode not in CYCLE_APPROVAL_MODES:
        return CYCLE_APPROVAL_MODES[0]
    return CYCLE_APPROVAL_MODES[
        (CYCLE_APPROVAL_MODES.index(mode) + 1) % len(CYCLE_APPROVAL_MODES)
    ]
