from __future__ import annotations

from io import StringIO

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from cora.cli import repl
from cora.cli.io import TerminalIO
from cora.cli.repl import COMMANDS
from cora.cli.ui.banner import BannerInfo, banner_lines
from cora.cli.ui.prompt import prompt_message
from cora.cli.ui.theme import THEMES, UNICODE_GLYPHS

INFO = BannerInfo(
    "0.1.0",
    "/tmp/project",
    ("cheap=mock/cheap", "strong=mock/strong"),
    "ask",
    "CORA.md",
    "main...origin/main (2 changed)",
)


def test_prompt_message_segments() -> None:
    th = THEMES["default"]
    assert prompt_message("> ", th) == [(th.pt_marker, "> ")]
    assert prompt_message("[plan] > ", th) == [(th.pt_mode, "[plan] "), (th.pt_marker, "> ")]
    assert prompt_message("... ", th) == [(th.pt_dim, "... ")]


def test_prompt_message_preserves_text() -> None:
    th = THEMES["default"]
    for p in ("> ", "[plan] > ", "... "):
        assert "".join(text for _, text in prompt_message(p, th)) == p


def test_prompt_constants() -> None:
    assert repl.PROMPT == "> "
    assert repl.PLAN_PROMPT == "[plan] > "


def test_multiline_hint_appears_once() -> None:
    assert "\n".join(banner_lines(INFO, UNICODE_GLYPHS, narrow=False)).count("Esc+Enter") == 1
    assert "\n".join(banner_lines(INFO, UNICODE_GLYPHS, narrow=True)).count("Esc+Enter") == 1


def test_terminal_read_with_plan_prompt(tmp_path) -> None:
    buf = StringIO()
    con = Console(file=buf, width=100, color_system=None, highlight=False)
    with create_pipe_input() as inp:
        tio = TerminalIO(
            tmp_path / "hist",
            list(COMMANDS),
            pt_input=inp,
            pt_output=DummyOutput(),
            console=con,
        )
        inp.send_text("ok\r")
        assert tio.read("[plan] > ") == "ok"
