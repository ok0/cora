from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from conftest import act, write_files
from cora.cli.io import PlainIO, TerminalIO
from cora.cli.repl import COMMANDS, Repl, ReplOptions
from cora.cli.ui.state import next_approval


class Feed:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.out: list[str] = []

    def read(self, prompt: str) -> str:
        self.out.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    @property
    def text(self) -> str:
        return "".join(self.out)


def make(ws, cfg, *, approval="ask") -> tuple[Repl, Feed]:
    feed = Feed()
    repl = Repl(
        PlainIO(input_fn=feed.read, write=feed.out.append),
        ReplOptions(Path(ws), Path(cfg), approval=approval),
    )
    return repl, feed


def _repl(tmp_path, ws, cfg, inp, approval="auto", width=100):
    buf = StringIO()
    con = Console(file=buf, width=width, color_system=None, highlight=False)
    tio = TerminalIO(
        tmp_path / "hist", list(COMMANDS), pt_input=inp, pt_output=DummyOutput(), console=con
    )
    return Repl(tio, ReplOptions(ws, cfg, approval=approval)), tio, buf


def test_next_approval_cycles() -> None:
    assert next_approval("ask") == "auto"
    assert next_approval("auto") == "deny"
    assert next_approval("deny") == "ask"
    assert next_approval("weird") == "ask"


def test_shift_tab_via_pipe(tmp_path, ws, cfg_file, scripted) -> None:
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp, approval="ask")
        inp.send_text("\x1b[Zx\r")
        assert tio.read("> ") == "x"
        assert repl.policy.mode == "auto" == repl.opts.approval
        assert "approval:auto" in tio.toolbar_text()
        inp.send_text("\x1b[Z\x1b[Zy\r")
        assert tio.read("> ") == "y"
        assert repl.policy.mode == "ask"


def test_shift_tab_deny_blocks_edit(ws, cfg_file, scripted) -> None:
    write_files(ws, {"a.txt": "MARKER\n"})
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "MARKER", "new": "EDITED"}),
        "Final Answer: done",
    ]
    repl, feed = make(ws, cfg_file, approval="ask")
    repl.cycle_approval()
    repl.cycle_approval()
    assert repl.policy.mode == "deny"
    repl.submit("edit")
    assert (Path(ws) / "a.txt").read_text(encoding="utf-8") == "MARKER\n"
    assert "failed: denied by user" in feed.text
    repl.dispatch("/reset")
    assert "approval: deny -> ask" in feed.text


def test_ctrl_t_toggle(tmp_path, ws, cfg_file, scripted) -> None:
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        inp.send_text("\x14z\r")
        assert tio.read("> ") == "z"
        assert repl.ui.show_todos is False
        assert "todo:off" in tio.toolbar_text()
        assert "on" in repl.toggle_todos()


def test_ctrl_l_keeps_session(tmp_path, ws, cfg_file, scripted) -> None:
    scripted.script[:] = ["Final Answer: one"]
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        repl.submit("first")
        before = json.dumps(repl.session.memory, sort_keys=True, default=str)
        sid = repl.session.id
        inp.send_text("\x0cq\r")
        assert tio.read("> ") == "q"
        assert json.dumps(repl.session.memory, sort_keys=True, default=str) == before
        assert repl.session.id == sid


def test_status_hint(tmp_path, ws, cfg_file, scripted) -> None:
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        tio.status_start("Thinking")
        assert tio._status.status == "Thinking (Ctrl+C to interrupt)"
        tio.status_stop()
