from __future__ import annotations

import io
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output

from cora.cli.repl import Repl, ReplOptions
from cora.cli.tui.app import TuiApp
from cora.cli.tui.io import TuiIO
from cora.cli.tui.transcript import Transcript

MOUSE_MODES_OFF = ("\x1b[?1000l", "\x1b[?1002l", "\x1b[?1003l", "\x1b[?1006l", "\x1b[?1015l")


class Harness:
    def __init__(self, tmp_path: Path, ws: Path, cfg: Path, *, approval: str = "auto",
                 size: tuple[int, int] = (120, 40), exit_summary: bool = True,
                 mouse: bool = True, scrollback: int = 5000) -> None:
        self.size = [Size(rows=size[1], columns=size[0])]
        self.buf = io.StringIO()
        self.output = Vt100_Output(self.buf, lambda: self.size[0], term="xterm-256color",
                                   enable_cpr=False)
        self._pipe_cm = create_pipe_input()
        self.pipe = self._pipe_cm.__enter__()
        self._pipe_open = True
        self.io = TuiIO(Transcript(scrollback), mouse=mouse)
        self.repl = Repl(self.io, ReplOptions(Path(ws), Path(cfg), approval=approval))
        self.tui = TuiApp(self.repl, self.io, history_path=tmp_path / "hist",
                          workdir=Path(ws), exit_summary=exit_summary,
                          pt_input=self.pipe, pt_output=self.output)
        self.code: int | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        def target() -> None:
            self.code = self.tui.run()
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()
        self.wait(lambda: self.io.waiting.is_set())
        self.wait(self._history_loaded)

    def _history_loaded(self) -> bool:
        task = self.tui.input._load_history_task
        return task is not None and task.done()

    def send(self, s: str) -> None:
        self.pipe.send_text(s)

    def line(self, s: str) -> None:
        self.send(s)
        self.wait(lambda: self.tui.input.text == s)
        self.send("\r")
        self.wait(lambda: self.tui.input.text == "")

    def wait(self, cond: Callable[[], bool], timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond():
                return
            time.sleep(0.02)
        raise AssertionError(f"condition not met; transcript tail:\n{self.text()[-800:]}")

    def idle(self) -> None:
        self.wait(lambda: self.io.waiting.is_set() and self.io.busy_since is None)

    @property
    def out(self) -> str:
        return self.buf.getvalue()

    def text(self) -> str:
        return self.io.transcript.plain_text()

    def screen(self) -> str:
        try:
            screen = self.tui.app.renderer.last_rendered_screen
        except AttributeError:
            return ""
        if screen is None:
            return ""
        size = self.size[0]
        rows = []
        for y in range(size.rows):
            row = screen.data_buffer[y]
            rows.append("".join(row[x].char for x in range(size.columns)).rstrip())
        return "\n".join(rows)

    def _rendered_style(self, locate: Callable[[str], int]) -> str | None:
        try:
            screen = self.tui.app.renderer.last_rendered_screen
        except AttributeError:
            return None
        if screen is None:
            loop = self.tui.app.loop
            if loop is not None:
                loop.call_soon_threadsafe(self.tui.app.invalidate)
            return None
        size = self.size[0]
        for y in reversed(range(size.rows)):
            row = screen.data_buffer[y]
            text = "".join(row[x].char for x in range(size.columns))
            idx = locate(text)
            if idx >= 0:
                return row[idx].style
        return None

    def _await_style(self, locate: Callable[[str], int], timeout: float = 10.0) -> str:
        deadline = time.monotonic() + timeout
        while True:
            style = self._rendered_style(locate)
            if style is not None:
                return style
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"no rendered row matched; screen tail:\n{self.screen()[-800:]}")
            time.sleep(0.02)

    def style_of(self, prefix: str) -> str:
        return self._await_style(lambda text: 0 if text.startswith(prefix) else -1)

    def style_at(self, needle: str) -> str:
        return self._await_style(lambda text: text.find(needle))

    def resize(self, cols: int, rows: int) -> None:
        self.size[0] = Size(rows=rows, columns=cols)
        self.tui.app.loop.call_soon_threadsafe(self.tui.app._on_resize)

    def finish(self, timeout: float = 10.0) -> int | None:
        assert self.thread is not None
        self.thread.join(timeout)
        assert not self.thread.is_alive()
        self._close_pipe()
        return self.code

    def _close_pipe(self) -> None:
        if self._pipe_open:
            self._pipe_open = False
            self._pipe_cm.__exit__(None, None, None)

    def close(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            self.tui.handle_signal(signal.SIGTERM)
            self.thread.join(10)
        self._close_pipe()

    def assert_restored(self, out: str) -> None:
        h = out.index("\x1b[?1049h")
        assert out.count("\x1b[?1049h") == 1
        for needle in ("\x1b[?1049l", "\x1b[?2004l", *MOUSE_MODES_OFF):
            assert needle in out[h:]
        last_on = out.rfind("\x1b[?1000h")
        if last_on >= 0:
            for needle in MOUSE_MODES_OFF:
                assert needle in out[last_on:]
