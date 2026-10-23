from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import IO

from rich.console import Console

from cora.core.config import UI_THEMES


@dataclass(frozen=True)
class Glyphs:
    ascii: bool
    tool: str
    tool_error: str
    result: str
    ellipsis: str
    sep: str
    dot: str
    todo_pending: str
    todo_active: str
    todo_done: str


UNICODE_GLYPHS = Glyphs(False, "●", "✗", "⎿", "…", "│", "·", "☐", "◐", "☒")
ASCII_GLYPHS = Glyphs(True, "*", "!", "|_", "...", "|", "-", "[ ]", "[~]", "[x]")


@dataclass(frozen=True)
class Theme:
    name: str
    accent: str
    dim: str
    tool: str
    error: str
    warn: str
    add: str
    remove: str
    hunk: str
    lineno: str
    mode: str
    todo_done: str
    todo_active: str
    todo_pending: str
    pt_marker: str
    pt_mode: str
    pt_dim: str


THEMES: dict[str, Theme] = {
    "default": Theme(
        "default",
        "bold cyan",
        "grey50",
        "green",
        "bold red",
        "yellow",
        "green",
        "red",
        "cyan",
        "grey50",
        "bold magenta",
        "green",
        "bold yellow",
        "",
        "ansicyan bold",
        "ansimagenta bold",
        "ansibrightblack",
    ),
    "dark": Theme(
        "dark",
        "bold bright_cyan",
        "grey62",
        "bright_green",
        "bold bright_red",
        "bright_yellow",
        "bright_green",
        "bright_red",
        "bright_cyan",
        "grey62",
        "bold bright_magenta",
        "bright_green",
        "bold bright_yellow",
        "",
        "ansibrightcyan bold",
        "ansibrightmagenta bold",
        "ansigray",
    ),
    "light": Theme(
        "light",
        "bold blue",
        "grey39",
        "dark_green",
        "bold red3",
        "dark_orange3",
        "dark_green",
        "red3",
        "blue",
        "grey39",
        "bold magenta",
        "dark_green",
        "bold dark_orange3",
        "",
        "ansiblue bold",
        "ansimagenta bold",
        "#666666",
    ),
    "mono": Theme("mono", *([""] * 16)),
}
assert tuple(THEMES) == UI_THEMES


def color_enabled(mode: str, *, isatty: bool, env: Mapping[str, str]) -> bool:
    if env.get("NO_COLOR"):
        return False
    if mode == "never":
        return False
    if mode == "always":
        return True
    return isatty


def unicode_supported(encoding: str | None) -> bool:
    return bool(encoding) and "utf" in encoding.lower()


def make_console(
    *,
    color: bool,
    force_terminal: bool = False,
    file: IO[str] | None = None,
    width: int | None = None,
) -> Console:
    return Console(
        file=file,
        width=width,
        highlight=False,
        color_system="auto" if color else None,
        force_terminal=True if force_terminal else None,
    )
