from __future__ import annotations

import asyncio
import threading

import pytest
from prompt_toolkit.formatted_text.utils import fragment_list_width

from cora.cli.common import CancelScope, run_interruptible
from cora.cli.tui.app import exit_summary_text
from cora.cli.tui.terminal import RESTORE_SEQUENCE, TerminalRestorer, osc52
from cora.cli.tui.transcript import OMITTED, ScrollState, Transcript
from cora.cli.ui.theme import THEMES, UNICODE_GLYPHS
from cora.cli.ui.toolview import ToolCallView
from cora.core.state import Session


def test_wrap_fits_width() -> None:
    t = Transcript()
    t.add_text("word " * 200)
    lines = t.lines(50, THEMES["default"], color=False)
    assert all(fragment_list_width(line) <= 50 for line in lines)
    assert len(t.lines(120, THEMES["default"], color=False)) < len(lines)


def test_scrollback_cap() -> None:
    t = Transcript(100)
    for i in range(150):
        t.add_text(f"line {i}")
    assert t.dropped == 50
    lines = t.lines(80, THEMES["default"], color=False)
    assert "".join(f[1] for f in lines[0]) == OMITTED


def test_scroll_state_follow_and_unseen() -> None:
    s = ScrollState()
    s.window(100, 20, 80)
    assert s.offset == 0
    s.scroll(10)
    s.window(105, 20, 80)
    assert s.offset == 15
    assert s.unseen is True
    s.to_bottom()
    assert s.following
    assert s.unseen is False


def test_theme_rerender() -> None:
    t = Transcript()
    t.add_rich(ToolCallView("read", "a.txt", True, "hello", THEMES["default"], UNICODE_GLYPHS))
    default = {frag[0] for line in t.lines(80, THEMES["default"], color=True) for frag in line}
    light = {frag[0] for line in t.lines(80, THEMES["light"], color=True) for frag in line}
    assert default != light


def test_expanded_tool_view_shows_all() -> None:
    output = "\n".join(f"line {i}" for i in range(30))
    t = Transcript()
    t.add_rich(ToolCallView("read", "big.txt", True, output, THEMES["default"], UNICODE_GLYPHS))
    assert "line 29" not in t.plain_text(expanded=False)
    assert "line 29" in t.plain_text(expanded=True)


def test_osc52() -> None:
    assert osc52("hi") == "\x1b]52;c;aGk=\x07"
    assert osc52("x" * 200_000) is None


def test_restorer_idempotent() -> None:
    written: list[str] = []
    restorer = TerminalRestorer(written.append, None)
    restorer.restore()
    restorer.restore()
    assert written == [RESTORE_SEQUENCE]


def test_exit_summary_text() -> None:
    session = Session(id="sess-1", task="t", meter=[{
        "ts": "t", "model": "m", "tier": "cheap", "purpose": "p", "input_tokens": 10,
        "output_tokens": 5, "cost_usd": 0.001, "price_known": True, "cost_source": "price",
    }])
    text = exit_summary_text(session, 1)
    assert "session: sess-1" in text
    assert "cora resume sess-1" in text
    assert "1 turn" in text
    assert "no session to resume" in exit_summary_text(None, 0)


def test_cancel_scope_interrupts_from_thread() -> None:
    scope = CancelScope()
    timer = threading.Timer(0.1, scope.cancel)
    timer.start()
    with pytest.raises(KeyboardInterrupt):
        run_interruptible(asyncio.sleep(10), scope)
    timer.join()
    assert not scope.active
