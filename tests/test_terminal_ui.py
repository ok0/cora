from __future__ import annotations

import re
from io import StringIO

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from conftest import act
from cora.cli.io import TerminalIO
from cora.cli.repl import COMMANDS, Repl, ReplOptions


def _repl(tmp_path, ws, cfg, inp, approval="auto", width=100):
    buf = StringIO()
    con = Console(file=buf, width=width, color_system=None, highlight=False)
    tio = TerminalIO(
        tmp_path / "hist", list(COMMANDS), pt_input=inp, pt_output=DummyOutput(), console=con
    )
    return Repl(tio, ReplOptions(ws, cfg, approval=approval)), tio, buf


def test_terminal_turn_with_toolbar(tmp_path, ws, cfg_file, scripted) -> None:
    scripted.script[:] = ["Final Answer: hi there"]
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        assert tio._session.bottom_toolbar == tio.toolbar_text
        repl._banner()
        assert "CORA 0.1.0" in buf.getvalue()
        inp.send_text("hello\r")
        line = repl._read()
        repl.submit(line)
        assert "hi there" in buf.getvalue()
        assert len(scripted.calls) == 1
        t = tio.toolbar_text()
        assert "\n" not in t
        assert "approval:auto" in t
        assert "cheap:mock/cheap" in t


def test_expand_after_collapsed(tmp_path, ws, cfg_file, scripted) -> None:
    for i in range(15):
        (ws / f"f{i:02d}.txt").write_text("x", encoding="utf-8")
    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        repl.submit("list")
        out = buf.getvalue()
        assert re.search(r"\+\d+ lines \(/expand\)", out)
        assert "● list_files()" in out
        assert "f14.txt" not in out
        repl.dispatch("/expand")
        assert "f14.txt" in buf.getvalue()
        assert len(scripted.calls) == 2
