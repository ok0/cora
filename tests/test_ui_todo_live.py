from __future__ import annotations

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


def test_todo_checklist_and_toggle(tmp_path, ws, cfg_file, scripted) -> None:
    scripted.script[:] = [
        act("todo_write", {"todos": [{"content": "step", "status": "in_progress"}]}),
        "Final Answer: ok",
    ]
    with create_pipe_input() as inp:
        repl, tio, buf = _repl(tmp_path, ws, cfg_file, inp)
        repl.submit("plan")
        assert "◐ step" in buf.getvalue()
        repl.toggle_todos()
        scripted.script[:] = [
            act("todo_write", {"todos": [{"content": "next", "status": "pending"}]}),
            "Final Answer: ok",
        ]
        repl.submit("again")
        out = buf.getvalue()
        assert "◐ next" not in out
        assert "☐ next" not in out
        assert out.count("● todo_write(") == 2
