from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, merge_completers
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_completions
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.output import ColorDepth, Output
from rich.console import Console, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.syntax import Syntax

from cora.cli.ui.diffview import diff_text
from cora.cli.ui.prompt import prompt_message
from cora.cli.ui.state import UiState
from cora.cli.ui.statusline import statusline, with_interrupt_hint
from cora.cli.ui.theme import color_enabled, make_console, unicode_supported
from cora.core.mentions import mention_candidates


class ReplIO(Protocol):
    def read(self, prompt: str) -> str: ...

    def ask(self, prompt: str) -> str: ...

    def print(self, text: str = "") -> None: ...

    def error(self, text: str) -> None: ...

    def markdown(self, text: str) -> None: ...

    def show_diff(self, text: str) -> None: ...

    def status_start(self, text: str) -> None: ...

    def status_stop(self) -> None: ...

    def stream_start(self) -> None: ...

    def stream_delta(self, text: str) -> None: ...

    def stream_end(self) -> None: ...

    def attach(self, ui: UiState) -> bool: ...

    def render(self, renderable: RenderableType) -> None: ...


def _stdin_input(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\r\n")


def _stdout_write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


class PlainIO:
    def __init__(
        self,
        input_fn: Callable[[str], str] | None = None,
        write: Callable[[str], None] | None = None,
    ) -> None:
        self._input = input_fn if input_fn is not None else _stdin_input
        self._write = write if write is not None else _stdout_write

    def read(self, prompt: str) -> str:
        return self._input(prompt)

    def ask(self, prompt: str) -> str:
        return self._input(prompt)

    def print(self, text: str = "") -> None:
        self._write(text + "\n")

    def error(self, text: str) -> None:
        self._write(text + "\n")

    def markdown(self, text: str) -> None:
        self.print(text)

    def show_diff(self, text: str) -> None:
        self._write(text if text.endswith("\n") else text + "\n")

    def status_start(self, text: str) -> None:
        return None

    def status_stop(self) -> None:
        return None

    def stream_start(self) -> None:
        return None

    def stream_delta(self, text: str) -> None:
        self._write(text)

    def stream_end(self) -> None:
        self._write("\n")

    def attach(self, ui: UiState) -> bool:
        return False

    def render(self, renderable: RenderableType) -> None:
        self.print(str(renderable))


class SlashCompleter(Completer):
    def __init__(self, names: Sequence[str]) -> None:
        self.names = list(names)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for name in self.names:
            if name.startswith(text):
                yield Completion(name, start_position=-len(text))


MENTION_TAIL = re.compile(r"(?<!\S)@(\S*)$")


class MentionCompleter(Completer):
    def __init__(self, root: Path) -> None:
        self.root = root

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        m = MENTION_TAIL.search(document.text_before_cursor)
        if m is None:
            return
        partial = m.group(1)
        for cand in mention_candidates(self.root, partial):
            yield Completion(cand, start_position=-len(partial))


class TerminalIO:
    def __init__(
        self,
        history_path: Path,
        commands: Sequence[str],
        *,
        workdir: Path | None = None,
        pt_input: Input | None = None,
        pt_output: Output | None = None,
        console: Console | None = None,
    ) -> None:
        self.ui: UiState | None = None
        history_path.parent.mkdir(parents=True, exist_ok=True)
        kb = KeyBindings()

        @kb.add("escape", "enter")
        def _newline(event) -> None:
            event.current_buffer.insert_text("\n")

        ui_on = Condition(lambda: self.ui is not None)

        @kb.add("s-tab", filter=ui_on & ~has_completions)
        def _cycle(event) -> None:
            self._on_key("approval")

        @kb.add("c-t", filter=ui_on)
        def _todos(event) -> None:
            self._on_key("todos")

        completer = (
            SlashCompleter(commands)
            if workdir is None
            else merge_completers([SlashCompleter(commands), MentionCompleter(workdir)])
        )
        self._session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_path)),
            completer=completer,
            complete_while_typing=True,
            key_bindings=kb,
            input=pt_input,
            output=pt_output,
        )
        self._console_injected = console is not None
        self.console = console if console is not None else Console(highlight=False)
        self._status = None
        self._live: Live | None = None
        self._buf = ""

    def attach(self, ui: UiState) -> bool:
        self.ui = ui
        color = color_enabled(ui.color_mode, isatty=sys.stdout.isatty(), env=os.environ)
        if not self._console_injected:
            self.console = make_console(
                color=color, force_terminal=color and ui.color_mode == "always"
            )
        if not unicode_supported(self.console.encoding):
            ui.ascii = True
        if not color:
            self._session.color_depth = ColorDepth.MONOCHROME
        self._session.bottom_toolbar = self.toolbar_text
        self._session.refresh_interval = 1.0
        return True

    def toolbar_text(self) -> str:
        if self.ui is None:
            return ""
        return statusline(self.ui, max(10, self._session.output.get_size().columns - 1))

    def _on_key(self, action: str) -> None:
        if self.ui is None:
            return
        cb = self.ui.on_cycle_approval if action == "approval" else self.ui.on_toggle_todos
        if cb is None:
            return
        msg = cb()
        run_in_terminal(lambda: self.print(msg))

    def render(self, renderable: RenderableType) -> None:
        self.console.print(renderable)

    def read(self, prompt: str) -> str:
        return self._session.prompt(
            prompt_message(prompt, self.ui.theme) if self.ui is not None else prompt
        )

    def ask(self, prompt: str) -> str:
        return self.console.input(prompt)

    def print(self, text: str = "") -> None:
        self.console.print(text, markup=False, highlight=False)

    def error(self, text: str) -> None:
        style = (self.ui.theme.warn or None) if self.ui is not None else "yellow"
        self.console.print(text, style=style, markup=False)

    def markdown(self, text: str) -> None:
        self.console.print(Markdown(text))

    def show_diff(self, text: str) -> None:
        if self.ui is None:
            self.console.print(Syntax(text, "diff", theme="ansi_dark", background_color="default"))
        else:
            self.console.print(diff_text(text, self.ui.theme))

    def status_start(self, text: str) -> None:
        text = with_interrupt_hint(text)
        if self._status is None:
            self._status = self.console.status(text)
            self._status.start()
        else:
            self._status.update(text)

    def status_stop(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    def stream_start(self) -> None:
        self._buf = ""
        self._live = Live(
            Markdown(""),
            console=self.console,
            refresh_per_second=12,
            vertical_overflow="visible",
        )
        self._live.start()

    def stream_delta(self, text: str) -> None:
        self._buf += text
        if self._live is not None:
            self._live.update(Markdown(self._buf))

    def stream_end(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None


def make_io(history_path: Path, commands: Sequence[str], workdir: Path | None = None) -> ReplIO:
    if sys.stdin.isatty() and sys.stdout.isatty():
        return TerminalIO(history_path, commands, workdir=workdir)
    return PlainIO()
