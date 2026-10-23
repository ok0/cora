from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

UiMode = Literal["tui", "classic", "plain"]
_TRUE = frozenset({"1", "true", "on", "yes"})
_FALSE = frozenset({"0", "false", "off", "no"})

def env_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None

def interactive_terminal(env: Mapping[str, str], *, stdin_tty: bool, stdout_tty: bool) -> bool:
    if not (stdin_tty and stdout_tty):
        return False
    return env.get("TERM", "").strip().lower() not in ("", "dumb")

def choose_ui(flag: bool | None, env: Mapping[str, str], config_tui: bool, *,
              stdin_tty: bool, stdout_tty: bool) -> UiMode:
    if not (stdin_tty and stdout_tty):
        return "plain"
    if env.get("TERM", "").strip().lower() in ("", "dumb"):
        return "classic"
    want = flag
    if want is None:
        want = env_flag(env.get("CORA_TUI"))
    if want is None:
        want = config_tui
    return "tui" if want else "classic"
