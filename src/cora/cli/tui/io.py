from __future__ import annotations

import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from rich.console import RenderableType

from cora.cli.common import CancelScope
from cora.cli.tui.terminal import osc52
from cora.cli.tui.transcript import Transcript
from cora.cli.ui.state import UiState
from cora.cli.ui.theme import color_enabled, unicode_supported
from cora.cli.ui.toolview import ToolCallView


@dataclass
class Approval:
    tool: str
    summary: str
    detail: str
    is_diff: bool
    done: threading.Event = field(default_factory=threading.Event)
    answer: str = "n"
    scroll: int = 0


@dataclass
class Ask:
    prompt: str
    done: threading.Event = field(default_factory=threading.Event)
    answer: str | None = None     # None means EOF/cancel


class TuiIO:
    """ReplIO for the TUI. Repl.run() calls it on the worker thread; the UI thread calls
    submit/answer_*/shutdown. Output goes to the Transcript (thread-safe)."""

    def __init__(self, transcript: Transcript, *, mouse: bool = False) -> None:
        self.transcript = transcript
        self.ui: UiState | None = None
        self.color = True
        self._initial_mouse = mouse
        self.cancel_scope = CancelScope()
        self.prompt = "> "
        self.waiting = threading.Event()
        self.closing = False
        self.busy_since: float | None = None
        self.phase = "Working"
        self.last_tool: str | None = None
        self.modal: Approval | None = None
        self.asking: Ask | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.on_change: Callable[[], None] = lambda: None
        self.post: Callable[[Callable[[], None]], None] = lambda fn: fn()
        self.write_raw: Callable[[str], None] | None = None

    @property
    def busy(self) -> bool:
        return not self.waiting.is_set() and self.asking is None and self.modal is None

    # ReplIO (worker thread)
    def attach(self, ui: UiState) -> bool:
        self.ui = ui
        self.color = color_enabled(ui.color_mode, isatty=True, env=os.environ)
        if not unicode_supported(getattr(sys.stdout, "encoding", None)):
            ui.ascii = True
        ui.show_todos = False
        ui.mouse = self._initial_mouse
        return True

    def read(self, prompt: str) -> str:
        if self.closing:
            raise EOFError
        self.prompt = prompt
        self.busy_since, self.phase, self.last_tool = None, "Working", None
        self.waiting.set()
        self.on_change()
        line = self._lines.get()
        self.waiting.clear()
        if line is None:
            raise EOFError
        return line

    def ask(self, prompt: str) -> str:
        if self.closing:
            raise EOFError
        a = Ask(prompt)
        self.asking = a
        self.on_change()
        a.done.wait()
        self.asking = None
        self.on_change()
        if a.answer is None:
            raise EOFError
        self.transcript.add_text(prompt + a.answer, "dim")
        return a.answer

    def approve(self, tool: str, summary: str, detail: str, is_diff: bool) -> str:
        g = self.ui.glyphs if self.ui is not None else None
        self.transcript.add_text(f"{g.tool if g else '●'} {tool} needs approval", "warn")
        if detail:
            (self.transcript.add_diff if is_diff else self.transcript.add_text)(detail)
        if self.closing:
            ans = "n"
        else:
            m = Approval(tool, summary, detail, is_diff)
            self.modal = m
            self.on_change()
            m.done.wait()
            self.modal = None
            ans = m.answer
        label = {"y": "allowed", "a": "allowed (always this session)"}.get(ans, "denied")
        self.transcript.add_text(f"  {g.result if g else '⎿'}  {label}", "dim")
        self.on_change()
        return ans

    def print(self, text: str = "") -> None:
        self.transcript.add_text(text)
        self.on_change()

    def error(self, text: str) -> None:
        self.transcript.add_text(text, "warn")
        self.on_change()

    def markdown(self, text: str) -> None:
        self.transcript.add_markdown(text)
        self.on_change()

    def show_diff(self, text: str) -> None:
        self.transcript.add_diff(text)
        self.on_change()

    def render(self, renderable: RenderableType) -> None:
        if isinstance(renderable, ToolCallView):
            self.last_tool = renderable.name
        self.transcript.add_rich(renderable)
        self.on_change()

    def status_start(self, text: str) -> None:
        self.phase = text
        self.on_change()

    def status_stop(self) -> None:
        self.on_change()

    def stream_start(self) -> None:
        self.phase = "Responding"
        self.transcript.stream_start()
        self.on_change()

    def stream_delta(self, text: str) -> None:
        self.transcript.stream_delta(text)
        self.on_change()

    def stream_end(self) -> None:
        self.transcript.stream_end()
        self.on_change()

    def copy_text(self, text: str) -> str:
        seq = osc52(text)
        if seq is None:
            return (f"The answer is too large for OSC 52 ({len(text)} chars); open Ctrl+O and "
                    "select it with your terminal instead.")
        writer = self.write_raw
        if writer is None:
            return "No terminal output is available for OSC 52."
        self.post(lambda: writer(seq))
        return (f"Copied the last answer ({len(text)} chars) with OSC 52. If the clipboard did "
                "not change, your terminal blocks OSC 52 (see USAGE.md, TUI).")

    # UI thread
    def submit(self, line: str) -> None:
        self.waiting.clear()
        self.busy_since = time.monotonic()
        self._lines.put(line)

    def answer_approval(self, answer: str) -> None:
        m = self.modal
        if m is not None:
            m.answer = answer
            m.done.set()

    def answer_ask(self, text: str | None) -> None:
        a = self.asking
        if a is not None:
            a.answer = text
            a.done.set()

    def shutdown(self) -> None:
        self.closing = True
        self.cancel_scope.cancel()
        self.answer_approval("n")
        self.answer_ask(None)
        self._lines.put(None)
