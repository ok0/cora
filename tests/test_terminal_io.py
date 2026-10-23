from __future__ import annotations

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from cora.cli.io import SlashCompleter, TerminalIO


def test_slash_completer():
    completer = SlashCompleter(["/model", "/help"])
    texts = [c.text for c in completer.get_completions(Document("/mo"), CompleteEvent())]
    assert texts == ["/model"]
    assert list(completer.get_completions(Document("hello /mo"), CompleteEvent())) == []


def test_terminal_io_history_and_newline(tmp_path):
    history = tmp_path / ".cora" / "history"
    with create_pipe_input() as inp:
        io = TerminalIO(history, ["/help"], pt_input=inp, pt_output=DummyOutput())
        inp.send_text("hello\r")
        assert io.read("> ") == "hello"
        inp.send_text("a\x1b\rb\r")
        assert io.read("> ") == "a\nb"
        inp.send_text("\x04")
        with pytest.raises(EOFError):
            io.read("> ")
    assert "+hello" in history.read_text(encoding="utf-8")

    with create_pipe_input() as inp2:
        io2 = TerminalIO(history, ["/help"], pt_input=inp2, pt_output=DummyOutput())
        inp2.send_text("\x1b[A\r")
        assert io2.read("> ") == "a\nb"
