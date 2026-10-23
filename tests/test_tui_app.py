from __future__ import annotations

import asyncio
import base64
import signal
import time
from pathlib import Path

import pytest

from conftest import CFG_TOML, act
from cora.cli.repl import Repl
from cora.cli.tui.transcript import WHEEL_LINES
from cora.core.providers import register_provider
from tui_harness import Harness

pytestmark = pytest.mark.slow


@register_provider("tui_slow")
class SlowProvider:
    def __init__(self, settings) -> None:
        pass

    async def complete(self, req):
        await asyncio.sleep(60)


SLOW_CFG = CFG_TOML.replace('"scripted"', '"tui_slow"')
STREAM_CFG = CFG_TOML.replace('"scripted"', '"scripted_stream"')
BIG_TEXT = "\n".join(f"line {i}" for i in range(30))
WHEEL_UP, WHEEL_DOWN = "\x1b[<64;10;5M", "\x1b[<65;10;5M"
MOUSE_ON_SEQS = ("\x1b[?1000h", "\x1b[?1003h", "\x1b[?1015h", "\x1b[?1006h")
PT_MOUSE_OFF_SEQS = ("\x1b[?1000l", "\x1b[?1003l", "\x1b[?1015l", "\x1b[?1006l")


def _write_cfg(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _row_style_at(h: Harness, needle: str) -> str:
    return h.style_at(needle)


@pytest.fixture
def make(tmp_path, ws, cfg_file):
    made: list[Harness] = []

    def factory(cfg: Path | None = None, **kwargs) -> Harness:
        h = Harness(tmp_path, ws, cfg or cfg_file, **kwargs)
        made.append(h)
        return h

    yield factory
    for h in made:
        h.close()


@pytest.mark.parametrize("path", ["exit", "eof", "ctrl_c_twice", "error", "sigterm", "sighup"])
def test_exit_paths_restore_terminal(path, make, monkeypatch, capsys) -> None:
    h = make()
    if path == "error":
        def boom(self, args):
            raise RuntimeError("boom")

        monkeypatch.setattr(Repl, "cmd_status", boom)
    h.start()
    h.idle()
    if path == "exit":
        h.line("/exit")
    elif path == "eof":
        h.send("\x04")
    elif path == "ctrl_c_twice":
        h.send("\x03\x03")
    elif path == "error":
        h.line("/status")
    elif path == "sigterm":
        h.tui.handle_signal(signal.SIGTERM)
    elif path == "sighup":
        h.tui.handle_signal(signal.SIGHUP)
    code = h.finish()
    expected = {"exit": 0, "eof": 0, "ctrl_c_twice": 0, "error": 1, "sigterm": 143, "sighup": 129}
    assert code == expected[path]
    assert "\x1b[?1000h" in h.out
    h.assert_restored(h.out)
    if path == "error":
        assert "boom" in capsys.readouterr().err


def test_two_turns_stream_and_stay_open(make, scripted, tmp_path) -> None:
    scripted.script.extend(["Final Answer: first answer", "Final Answer: second answer"])
    h = make(cfg=_write_cfg(tmp_path, "stream.toml", STREAM_CFG))
    h.start()
    h.line("one")
    h.wait(lambda: "first answer" in h.text())
    h.idle()
    h.line("two")
    h.wait(lambda: "second answer" in h.text())
    h.idle()
    assert h.repl.turns == 2
    assert h.thread.is_alive()
    assert any(b.kind == "markdown" for b in h.io.transcript._blocks)
    h.line("/exit")
    assert h.finish() == 0


def test_ctrl_c_interrupts_running_turn(make, tmp_path) -> None:
    h = make(cfg=_write_cfg(tmp_path, "slow.toml", SLOW_CFG))
    h.start()
    h.line("go")
    h.wait(lambda: h.io.cancel_scope.active)
    h.send("\x03")
    h.wait(lambda: "Interrupted." in h.text())
    h.idle()
    assert h.thread.is_alive()


def test_ctrl_c_clears_input_then_double_quits(make) -> None:
    h = make()
    h.start()
    h.send("abc")
    h.wait(lambda: h.tui.input.text == "abc")
    h.send("\x03")
    h.wait(lambda: h.tui.input.text == "")
    assert h.thread.is_alive()
    h.send("\x03\x03")
    assert h.finish() == 0


def test_ctrl_d(make) -> None:
    h = make()
    h.start()
    h.send("x")
    h.wait(lambda: h.tui.input.text == "x")
    h.send("\x04")
    time.sleep(0.3)
    assert h.thread.is_alive()
    h.send("\x03")
    h.send("\x04")
    assert h.finish() == 0


def test_pageup_stops_follow_and_ctrl_end_resumes(make) -> None:
    h = make(size=(120, 20))
    h.start()
    h.line("/help")
    h.idle()
    h.send("\x1b[5~")
    h.wait(lambda: h.tui.main_scroll.offset > 0)
    h.io.print("late line")
    h.wait(lambda: h.tui.main_scroll.unseen and "new output" in h.screen())
    h.send("\x1b[1;5F")
    h.wait(lambda: h.tui.main_scroll.following and not h.tui.main_scroll.unseen)


def test_ctrl_o_viewer_shows_full_tool_output(make, ws, scripted) -> None:
    (ws / "big.txt").write_text(BIG_TEXT + "\n", encoding="utf-8")
    scripted.script.extend([act("read_file", {"path": "big.txt"}), "Final Answer: read"])
    h = make()
    h.start()
    h.line("read it")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    assert "line 29" not in h.text()
    h.send("\x0f")
    h.wait(lambda: "Transcript (full)" in h.screen() and "line 29" in h.screen())
    h.send("q")
    h.wait(lambda: not h.tui.viewer_open)


def test_mouse_default_on_and_toggle(make) -> None:
    h = make()
    h.start()
    h.idle()
    h.wait(lambda: "mouse:on" in h.screen())
    assert h.out.count("\x1b[?1000h") == 1
    for seq in MOUSE_ON_SEQS:
        assert seq in h.out
    i = len(h.out)
    h.line("/mouse off")
    h.wait(lambda: "mouse:off" in h.screen() and "\x1b[?1000l" in h.out[i:])
    for seq in PT_MOUSE_OFF_SEQS:
        assert seq in h.out[i:]
    j = len(h.out)
    h.line("/mouse on")
    h.wait(lambda: "mouse:on" in h.screen() and "\x1b[?1000h" in h.out[j:])
    for seq in MOUSE_ON_SEQS:
        assert seq in h.out[j:]
    k = len(h.out)
    h.send("\x1bOQ")
    h.wait(lambda: "mouse:off" in h.screen() and "\x1b[?1000l" in h.out[k:])


def test_mouse_off_config_emits_no_mouse_modes(make) -> None:
    h = make(mouse=False)
    h.start()
    h.idle()
    h.wait(lambda: "mouse:off" in h.screen())
    for seq in MOUSE_ON_SEQS:
        assert seq not in h.out
    h.line("/exit")
    assert h.finish() == 0
    h.assert_restored(h.out)


def _fill(h: Harness, n: int = 100) -> None:
    for i in range(n):
        h.io.print(f"row {i}")
    h.wait(lambda: "row 99" in h.screen())


def test_wheel_scrolls_transcript_and_follow(make) -> None:
    h = make(size=(120, 20))
    h.start()
    h.idle()
    _fill(h)
    h.send(WHEEL_UP * 3)
    h.wait(lambda: h.tui.main_scroll.offset == 3 * WHEEL_LINES)
    assert not h.tui.main_scroll.following
    h.io.print("late line")
    h.wait(lambda: h.tui.main_scroll.unseen and "new output" in h.screen())
    h.send(WHEEL_DOWN * 4)
    h.wait(lambda: h.tui.main_scroll.following and not h.tui.main_scroll.unseen
           and "late line" in h.screen())


def test_wheel_never_touches_input_history(make, tmp_path) -> None:
    (tmp_path / "hist").write_text("\n# 2026\n+old entry\n", encoding="utf-8")
    h = make(size=(120, 20))
    h.start()
    h.idle()
    _fill(h)
    before = h.tui.input.working_index
    h.send(WHEEL_UP * 3 + WHEEL_DOWN)
    h.wait(lambda: h.tui.main_scroll.offset == 2 * WHEEL_LINES)
    assert h.tui.input.text == ""
    assert h.tui.input.working_index == before
    h.send("draft")
    h.wait(lambda: h.tui.input.text == "draft")
    # wheel over the input (row 19) and status (row 20) rows, clicks on transcript and input
    h.send("\x1b[<64;5;19M\x1b[<65;5;19M\x1b[<64;5;20M"
           "\x1b[<0;10;5M\x1b[<0;10;5m\x1b[<0;5;19M\x1b[<0;5;19m")
    h.send(WHEEL_UP)
    h.wait(lambda: h.tui.main_scroll.offset == 3 * WHEEL_LINES)
    assert h.tui.input.text == "draft"
    assert h.tui.input.working_index == before
    h.send("\x03")
    h.wait(lambda: h.tui.input.text == "")
    h.send("\x1b[A")
    h.wait(lambda: h.tui.input.text == "old entry")


def test_wheel_scrolls_viewer(make) -> None:
    h = make(size=(120, 20))
    h.start()
    h.idle()
    _fill(h)
    h.send("\x0f")
    h.wait(lambda: h.tui.viewer_open and "Transcript (full)" in h.screen())
    h.send(WHEEL_UP * 2)
    h.wait(lambda: h.tui.viewer_scroll.offset == 2 * WHEEL_LINES)
    h.send(WHEEL_DOWN)
    h.wait(lambda: h.tui.viewer_scroll.offset == WHEEL_LINES)
    assert h.tui.main_scroll.offset == 0
    h.send("q")
    h.wait(lambda: not h.tui.viewer_open)


def test_wheel_scrolls_approval_preview(make, ws, scripted) -> None:
    body = "".join(f"line {i}\n" for i in range(40))
    (ws / "a.txt").write_text(body, encoding="utf-8")
    scripted.script.extend([
        act("edit_file", {"path": "a.txt", "old": body, "new": "x\n"}),
        "Final Answer: done",
    ])
    h = make(approval="ask", size=(120, 24))
    h.start()
    h.line("edit")
    h.wait(lambda: h.io.modal is not None and "needs approval" in h.screen())
    rows = h.screen().split("\n")
    y = next(i for i, r in enumerate(rows) if r.startswith("│--- a/a.txt")) + 1
    h.send(f"\x1b[<65;10;{y}M" * 2)
    h.wait(lambda: h.io.modal is not None and h.io.modal.scroll == 2 * WHEEL_LINES)
    h.send(f"\x1b[<64;10;{y}M")
    h.wait(lambda: h.io.modal is not None and h.io.modal.scroll == WHEEL_LINES)
    h.send("n")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    assert (ws / "a.txt").read_text(encoding="utf-8") == body


def test_copy_sends_osc52(make, scripted) -> None:
    scripted.script.append("Final Answer: copy me")
    h = make()
    h.start()
    h.line("q")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    h.line("/copy")
    payload = base64.b64encode(b"copy me").decode("ascii")
    h.wait(lambda: "\x1b]52;c;" + payload in h.out)


def _approval_setup(ws: Path, scripted) -> None:
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    scripted.script.extend([
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: done",
    ])


def test_approval_yes(make, ws, scripted, cfg_file_gates_off) -> None:
    _approval_setup(ws, scripted)
    h = make(cfg=cfg_file_gates_off, approval="ask")
    h.start()
    h.line("edit")
    h.wait(lambda: h.io.modal is not None)
    h.wait(lambda: "needs approval" in h.screen())
    assert "ansigreen" in _row_style_at(h, "+ bye")
    h.send("y")
    h.wait(lambda: "done" in h.text())
    h.idle()
    assert (ws / "a.txt").read_text(encoding="utf-8") == "bye\n"


@pytest.mark.parametrize("key", ["n", "\x1b"])
def test_approval_no_and_escape(key, make, ws, scripted) -> None:
    _approval_setup(ws, scripted)
    h = make(approval="ask")
    h.start()
    h.line("edit")
    h.wait(lambda: h.io.modal is not None)
    h.send(key)
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    assert (ws / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert "denied by user" in str(scripted.calls[-1].messages)


def test_shift_tab_cycles_and_updates_status(make) -> None:
    h = make(approval="ask")
    h.start()
    h.send("\x1b[Z")
    h.wait(lambda: h.repl.policy.mode == "auto" and "approval:auto" in h.screen())


def test_expand(make, ws, scripted) -> None:
    (ws / "big.txt").write_text(BIG_TEXT + "\n", encoding="utf-8")
    scripted.script.extend([act("read_file", {"path": "big.txt"}), "Final Answer: read"])
    h = make()
    h.start()
    h.line("read it")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    h.line("/expand")
    h.wait(lambda: "line 29" in h.text())


def test_theme_changes_prompt_style(make) -> None:
    h = make()
    h.start()
    h.idle()
    assert "ansicyan" in h.style_of("> ")
    h.line("/theme light")
    h.wait(lambda: "ansiblue" in h.style_of("> "))


def test_ctrl_t_toggles_todo_panel(make) -> None:
    h = make()
    h.start()
    h.send("\x14")
    h.wait(lambda: h.repl.ui.show_todos and "TODO (Ctrl+T hides)" in h.screen())
    h.send("\x14")
    h.wait(lambda: "TODO (Ctrl+T hides)" not in h.screen())


def test_ctrl_l_resumes_follow(make) -> None:
    h = make(size=(120, 20))
    h.start()
    h.line("/help")
    h.idle()
    h.send("\x1b[5~")
    h.wait(lambda: h.tui.main_scroll.offset > 0)
    h.send("\x0c")
    h.wait(lambda: h.tui.main_scroll.offset == 0)


def test_history_up(make, tmp_path) -> None:
    (tmp_path / "hist").write_text("\n# 2026\n+old entry\n", encoding="utf-8")
    h = make()
    h.start()
    h.send("\x1b[A")
    h.wait(lambda: h.tui.input.text == "old entry")


def test_multiline_and_paste_do_not_submit(make, scripted) -> None:
    h = make()
    h.start()
    h.send("a\x1b\rb")
    h.wait(lambda: h.tui.input.text == "a\nb")
    h.send("\x03")
    h.send("x\ny")
    h.wait(lambda: h.tui.input.text == "x\ny")
    h.send("\x03")
    h.send("\x1b[200~p\nq\x1b[201~")
    h.wait(lambda: h.tui.input.text == "p\nq")
    assert scripted.calls == []


def test_completion_menus(make, ws) -> None:
    h = make()
    h.start()
    h.send("/he")

    def has(text: str) -> bool:
        state = h.tui.input.complete_state
        return state is not None and any(c.text == text for c in state.completions)

    h.wait(lambda: has("/help"))
    h.send("\x03")
    (ws / "abc.txt").write_text("x", encoding="utf-8")
    h.send("see @ab")
    h.wait(lambda: has("abc.txt"))


def test_resize_sequence(make) -> None:
    h = make(size=(120, 40))
    h.start()
    h.idle()
    for cols, rows in [(120, 40), (50, 15), (38, 9), (120, 40)]:
        h.resize(cols, rows)
        if (cols, rows) == (38, 9):
            h.wait(lambda: "Terminal too small" in h.screen())
        else:
            h.wait(lambda: "approval:" in h.screen() and "too small" not in h.screen())
    assert h.tui.error is None
    assert h.thread.is_alive()


def test_exit_summary_after_restore(make, scripted) -> None:
    scripted.script.append("Final Answer: secret transcript text")
    h = make()
    h.start()
    h.line("hi")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    h.line("/exit")
    h.finish()
    tail = h.out.rsplit("\x1b[?1049l", 1)[1]
    assert f"session: {h.repl.session.id}" in tail
    assert "cora resume" in tail
    assert "secret transcript text" not in tail


def test_exit_summary_disabled(make, scripted) -> None:
    scripted.script.append("Final Answer: secret transcript text")
    h = make(exit_summary=False)
    h.start()
    h.line("hi")
    h.wait(lambda: h.repl.turns == 1)
    h.idle()
    h.line("/exit")
    h.finish()
    tail = h.out.rsplit("\x1b[?1049l", 1)[1]
    assert "session:" not in tail
