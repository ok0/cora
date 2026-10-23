from __future__ import annotations

import asyncio
import contextlib
import functools
import io
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.filters import Condition, has_completions, is_searching
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    DynamicContainer,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import (
    BufferControl,
    FormattedTextControl,
    UIContent,
    UIControl,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.styles import DynamicStyle, Style
from prompt_toolkit.widgets import Frame, SearchToolbar
from rich.text import Text

from cora.cli.io import MentionCompleter, SlashCompleter
from cora.cli.repl import COMMANDS, Repl, ReplOptions
from cora.cli.tui.io import TuiIO
from cora.cli.tui.terminal import TerminalRestorer
from cora.cli.tui.transcript import (
    WHEEL_LINES,
    ScrollState,
    Transcript,
    TranscriptControl,
    render_lines,
)
from cora.cli.ui.diffview import diff_text
from cora.cli.ui.prompt import prompt_message
from cora.cli.ui.statusline import INTERRUPT_HINT, statusline
from cora.cli.ui.theme import Theme
from cora.cli.ui.todoview import todo_text
from cora.core.config import UiSettings
from cora.core.metering import CostMeter
from cora.core.state import Session

CTRL_C_WINDOW_S = 2.0
MIN_COLUMNS, MIN_ROWS = 40, 10
SIDEBAR_MIN_COLUMNS = 100
SIDEBAR_WIDTH = 32
INPUT_MAX_ROWS = 8
FORCE_EXIT_AFTER_S = 5.0
SPINNER, ASCII_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "|/-\\"
EXIT_CODES = {"sigterm": 143, "sighup": 129, "sigint": 130}
BUSY_MESSAGE = "A turn is running; wait for it or press Ctrl+C to interrupt (your input was kept)."
CTRL_C_HINT = "(press Ctrl+C again to quit; Ctrl+D or /exit also quits)"
MOUSE_ON = ("mouse capture: on (the wheel scrolls the transcript; to select text, drag with "
            "Shift or Option held, depending on your terminal; /copy copies the last answer; "
            "F2 or /mouse off releases the mouse)")
MOUSE_OFF = ("mouse capture: off (your terminal selects and copies text as usual; the wheel "
             "may act as Up/Down and move through input history; F2 or /mouse on re-enables)")
APPROVAL_KEYS = ("[y] allow  [n] deny  [a] always this session  [Esc] deny  "
                 "↑/↓ PgUp/PgDn scroll  Shift+Tab approval mode")


@functools.lru_cache(maxsize=8)
def pt_style(theme: Theme) -> Style:
    return Style.from_dict({
        "status": theme.pt_dim, "running": theme.pt_mode, "hint": theme.pt_dim,
        "modal.title": f"bold {theme.pt_mode}".strip(), "frame.border": theme.pt_marker,
    })


def exit_summary_text(session: Session | None, turns: int) -> str:
    noun = "turn" if turns == 1 else "turns"
    if session is None:
        return f"CORA: {turns} {noun}; no session to resume.\n"
    meter = session.meter
    inp = sum(int(r.get("input_tokens", 0)) for r in meter)
    out = sum(int(r.get("output_tokens", 0)) for r in meter)
    cost = CostMeter.from_list(meter).total_cost_usd if meter else 0.0
    unknown = " +unknown" if any(not r.get("price_known", True) for r in meter) else ""
    return (f"CORA: {turns} {noun} · {inp} in / {out} out tokens · ${cost:.4f}{unknown}\n"
            f"session: {session.id} (resume: cora resume {session.id}, "
            f"or /resume {session.id} inside cora)\n")


class _StderrToTranscript(io.TextIOBase):
    def __init__(self, tio: TuiIO) -> None:
        self._io, self._buf = tio, ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._io.error(line)
        return len(s)

    def flush(self) -> None:
        return None


class _PreviewControl(UIControl):
    def __init__(self, tui: TuiApp) -> None:
        self.tui = tui
        self._cache: dict[tuple, list[StyleAndTextTuples]] = {}

    def create_content(self, width: int, height: int) -> UIContent:
        m = self.tui.io.modal
        if m is None or not m.detail:
            return UIContent(line_count=1)
        theme = self.tui.ui.theme
        color = self.tui.io.color
        key = (id(m), width, theme.name, color)
        lines = self._cache.get(key)
        if lines is None:
            renderable = diff_text(m.detail, theme) if m.is_diff else Text(m.detail)
            lines = render_lines(renderable, width, color=color)
            self._cache[key] = lines
        m.scroll = max(0, min(m.scroll, max(0, len(lines) - height)))
        visible = lines[m.scroll:m.scroll + height]
        return UIContent(get_line=lambda i: visible[i] if 0 <= i < len(visible) else [],
                         line_count=max(1, len(visible)), show_cursor=False)

    def mouse_handler(self, mouse_event: MouseEvent):
        m = self.tui.io.modal
        if m is None:
            return NotImplemented
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            m.scroll = max(0, m.scroll - WHEEL_LINES)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            m.scroll += WHEEL_LINES
            return None
        return NotImplemented


class TuiApp:
    def __init__(
        self,
        repl: Repl,
        io: TuiIO,
        *,
        history_path: Path,
        workdir: Path,
        exit_summary: bool = True,
        pt_input: Input | None = None,
        pt_output: Output | None = None,
    ) -> None:
        self.repl = repl
        self.io = io
        self.ui = repl.ui
        self.exit_summary = exit_summary
        self.viewer_open = False
        self.main_scroll = ScrollState()
        self.viewer_scroll = ScrollState()
        self.exit_reason: str | None = None
        self.error: str | None = None
        self.code: int | None = None
        self._ctrl_c_at: float | None = None
        self._worker_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._old_signals: dict[int, Any] = {}
        self._pt_input = pt_input
        history_path.parent.mkdir(parents=True, exist_ok=True)
        self.input = Buffer(
            multiline=True,
            history=FileHistory(str(history_path)),
            completer=merge_completers([SlashCompleter(list(COMMANDS)),
                                        MentionCompleter(workdir)]),
            complete_while_typing=True,
        )
        self.search = SearchToolbar()
        input_window = Window(
            BufferControl(self.input, search_buffer_control=self.search.control),
            height=lambda: Dimension(min=1, max=INPUT_MAX_ROWS,
                                     preferred=self.input.document.line_count),
            wrap_lines=True,
            dont_extend_height=True,
        )
        prompt_window = Window(FormattedTextControl(self._prompt_text), dont_extend_width=True)
        approving = Condition(lambda: io.modal is not None)
        asking = Condition(lambda: io.asking is not None)
        viewer = Condition(lambda: self.viewer_open)
        too_small = Condition(self._too_small)
        running = Condition(lambda: self._worker_thread is not None and io.busy)
        has_detail = Condition(lambda: io.modal is not None and bool(io.modal.detail))
        self._transcript_window = Window(
            TranscriptControl(lambda w: self._lines(w, False), self.main_scroll),
            wrap_lines=False, always_hide_cursor=True,
        )
        self._todo_window_side = Window(
            FormattedTextControl(self._todo_fragments), width=SIDEBAR_WIDTH, wrap_lines=True,
        )
        self._todo_window_top = Window(
            FormattedTextControl(self._todo_fragments), height=Dimension(max=6), wrap_lines=True,
        )
        body = DynamicContainer(self._body)
        approval_panel = ConditionalContainer(
            Frame(
                HSplit([
                    Window(FormattedTextControl(self._approval_header), wrap_lines=True,
                           dont_extend_height=True),
                    ConditionalContainer(
                        Window(_PreviewControl(self), height=self._preview_height),
                        filter=has_detail,
                    ),
                    Window(FormattedTextControl(lambda: [("class:hint", APPROVAL_KEYS)]),
                           height=1),
                ]),
                title="Approval required",
            ),
            filter=approving,
        )
        ask_box = ConditionalContainer(
            Frame(
                Window(
                    FormattedTextControl(
                        lambda: [("class:modal.title", io.asking.prompt if io.asking else "")]
                    ),
                    wrap_lines=True, dont_extend_height=True,
                ),
                title="Question",
            ),
            filter=asking,
        )
        normal = HSplit([
            body,
            ConditionalContainer(Window(FormattedTextControl(self._running_text), height=1),
                                 filter=running),
            ask_box,
            approval_panel,
            ConditionalContainer(
                HSplit([VSplit([prompt_window, input_window]), self.search]),
                filter=~approving,
            ),
            Window(FormattedTextControl(self._status_text), height=1, style="class:status"),
        ])
        viewer_stack = HSplit([
            Window(FormattedTextControl(lambda: [(
                "reverse",
                " Transcript (full) · ↑/↓ PgUp/PgDn g/G move · q or Esc closes ",
            )]), height=1),
            Window(TranscriptControl(lambda w: self._lines(w, True), self.viewer_scroll),
                   wrap_lines=False, always_hide_cursor=True),
        ])
        main = HSplit([
            ConditionalContainer(normal, filter=~viewer),
            ConditionalContainer(viewer_stack, filter=viewer),
        ])
        root = FloatContainer(
            content=HSplit([
                ConditionalContainer(main, filter=~too_small),
                ConditionalContainer(
                    Window(FormattedTextControl(self._small_text), wrap_lines=True),
                    filter=too_small,
                ),
            ]),
            floats=[Float(xcursor=True, ycursor=True,
                          content=CompletionsMenu(max_height=8, scroll_offset=1))],
        )
        self.app: Application[None] = Application(
            layout=Layout(root, focused_element=input_window),
            key_bindings=self._bindings(approving, asking, viewer),
            style=DynamicStyle(lambda: pt_style(self.ui.theme)),
            full_screen=True,
            mouse_support=Condition(lambda: bool(self.ui.mouse)),
            color_depth=lambda: None if self.io.color else ColorDepth.MONOCHROME,
            refresh_interval=0.5,
            enable_page_navigation_bindings=False,
            input=pt_input,
            output=pt_output,
        )

    def _size(self) -> Any:
        return self.app.output.get_size()

    def _too_small(self) -> bool:
        s = self._size()
        return s.columns < MIN_COLUMNS or s.rows < MIN_ROWS

    def _small_text(self) -> StyleAndTextTuples:
        s = self._size()
        return [("", f"Terminal too small: {s.columns}x{s.rows}. CORA needs at least "
                     f"{MIN_COLUMNS}x{MIN_ROWS}; enlarge the window (Ctrl+D quits).")]

    def _lines(self, width: int, expanded: bool) -> list[StyleAndTextTuples]:
        return self.io.transcript.lines(width, self.ui.theme, color=self.io.color,
                                        expanded=expanded)

    def _body(self) -> Any:
        if not self.ui.show_todos:
            return self._transcript_window
        if self._size().columns >= SIDEBAR_MIN_COLUMNS:
            return VSplit([
                self._transcript_window,
                Window(width=1, char="│", style="class:hint"),
                self._todo_window_side,
            ])
        return HSplit([
            Frame(self._todo_window_top, title="TODO"),
            self._transcript_window,
        ])

    def _todo_fragments(self) -> StyleAndTextTuples:
        out: StyleAndTextTuples = [("class:modal.title", "TODO (Ctrl+T hides)\n")]
        items = self.ui.get_todos() if self.ui.get_todos else []
        for line in render_lines(todo_text(items, self.ui.theme, self.ui.glyphs),
                                 SIDEBAR_WIDTH - 1, color=self.io.color):
            out.extend(line + [("", "\n")])
        return out

    def _prompt_text(self) -> StyleAndTextTuples:
        if self.io.asking is not None:
            return [("class:modal.title", "› ")]
        return prompt_message(self.io.prompt, self.ui.theme)

    def _status_text(self) -> StyleAndTextTuples:
        self.ui.unseen = self.main_scroll.unseen
        return [("class:status", statusline(self.ui, max(10, self._size().columns - 1)))]

    def _running_text(self) -> StyleAndTextTuples:
        frames = ASCII_SPINNER if self.ui.ascii else SPINNER
        now = time.monotonic()
        frame = frames[int(now * 8) % len(frames)]
        started = self.io.busy_since if self.io.busy_since is not None else now
        elapsed = now - started
        phase = self.io.phase + (f" · last tool: {self.io.last_tool}"
                                 if self.io.last_tool else "")
        return [("class:running", f"{frame} {phase} · {elapsed:.0f}s · {INTERRUPT_HINT}")]

    def _approval_header(self) -> StyleAndTextTuples:
        m = self.io.modal
        if m is None:
            return []
        glyphs = self.ui.glyphs
        return [("class:modal.title", f"{glyphs.tool} {m.tool} needs approval\n"),
                ("class:hint", m.summary[:300])]

    def _preview_height(self) -> Dimension:
        m = self.io.modal
        if m is None:
            return Dimension.exact(0)
        return Dimension(min=1, max=max(3, self._size().rows - 12),
                         preferred=m.detail.count("\n") + 1)

    def _bindings(self, approving: Condition, asking: Condition,
                  viewer: Condition) -> KeyBindings:
        kb = KeyBindings()
        normal = ~approving & ~viewer
        io = self.io

        @kb.add("<any>", filter=viewer | approving)
        def _swallow(event) -> None:
            return None

        @kb.add("enter", filter=normal & ~is_searching)
        def _enter(event) -> None:
            self._on_enter()

        @kb.add("escape", "enter", filter=normal)
        @kb.add("c-j", filter=normal)
        def _newline(event) -> None:
            self.input.insert_text("\n")

        @kb.add("tab", filter=normal)
        def _tab(event) -> None:
            if self.input.complete_state:
                self.input.complete_next()
            else:
                self.input.start_completion(select_first=False)

        @kb.add("s-tab", filter=has_completions & normal)
        def _prev_completion(event) -> None:
            self.input.complete_previous()

        @kb.add("s-tab", filter=~has_completions)
        def _cycle(event) -> None:
            msg = self.ui.on_cycle_approval()
            if msg:
                io.print(msg)

        @kb.add("c-c", filter=~is_searching)
        def _ctrl_c(event) -> None:
            self._on_ctrl_c()

        @kb.add("c-d", filter=normal & Condition(lambda: not self.input.text))
        def _ctrl_d(event) -> None:
            self._on_ctrl_d()

        @kb.add("c-t")
        def _todos(event) -> None:
            io.print(self.ui.on_toggle_todos())

        @kb.add("c-l")
        def _redraw(event) -> None:
            self.main_scroll.to_bottom()
            event.app.renderer.clear()

        @kb.add("c-o", filter=~approving)
        def _viewer(event) -> None:
            self.viewer_open = True
            self.viewer_scroll.to_bottom()

        @kb.add("f2")
        def _f2(event) -> None:
            self._set_mouse(not self.ui.mouse)

        @kb.add("pageup", filter=normal)
        def _pgup(event) -> None:
            self.main_scroll.scroll(max(1, self.main_scroll.height - 1))

        @kb.add("pagedown", filter=normal)
        def _pgdn(event) -> None:
            self.main_scroll.scroll(-max(1, self.main_scroll.height - 1))

        @kb.add("c-up", filter=normal)
        @kb.add("escape", "up", filter=normal)
        def _up(event) -> None:
            self.main_scroll.scroll(1)

        @kb.add("c-down", filter=normal)
        @kb.add("escape", "down", filter=normal)
        def _down(event) -> None:
            self.main_scroll.scroll(-1)

        @kb.add("c-end", filter=normal)
        def _bottom(event) -> None:
            self.main_scroll.to_bottom()

        @kb.add("up", filter=viewer)
        def _v_up(event) -> None:
            self.viewer_scroll.scroll(1)

        @kb.add("down", filter=viewer)
        def _v_down(event) -> None:
            self.viewer_scroll.scroll(-1)

        @kb.add("pageup", filter=viewer)
        def _v_pgup(event) -> None:
            self.viewer_scroll.scroll(max(1, self.viewer_scroll.height - 1))

        @kb.add("pagedown", filter=viewer)
        def _v_pgdn(event) -> None:
            self.viewer_scroll.scroll(-max(1, self.viewer_scroll.height - 1))

        @kb.add("g", filter=viewer)
        def _v_top(event) -> None:
            self.viewer_scroll.to_top()

        @kb.add("G", filter=viewer)
        def _v_bottom(event) -> None:
            self.viewer_scroll.to_bottom()

        @kb.add("q", filter=viewer)
        @kb.add("escape", filter=viewer)
        def _v_close(event) -> None:
            self.viewer_open = False

        @kb.add("y", filter=approving)
        def _yes(event) -> None:
            io.answer_approval("y")

        @kb.add("a", filter=approving)
        def _always(event) -> None:
            io.answer_approval("a")

        @kb.add("n", filter=approving)
        @kb.add("escape", filter=approving)
        def _no(event) -> None:
            io.answer_approval("n")

        @kb.add("up", filter=approving)
        def _m_up(event) -> None:
            if io.modal is not None:
                io.modal.scroll -= 1

        @kb.add("down", filter=approving)
        def _m_down(event) -> None:
            if io.modal is not None:
                io.modal.scroll += 1

        @kb.add("pageup", filter=approving)
        def _m_pgup(event) -> None:
            if io.modal is not None:
                io.modal.scroll -= 10

        @kb.add("pagedown", filter=approving)
        def _m_pgdn(event) -> None:
            if io.modal is not None:
                io.modal.scroll += 10

        return kb

    def _on_enter(self) -> None:
        io, text = self.io, self.input.text
        if io.asking is not None:
            self.input.reset()
            io.answer_ask(text)
            return
        words = text.strip().split()
        if words and words[0] == "/mouse":
            self.input.reset(append_to_history=True)
            io.transcript.add_text(io.prompt + text.strip(), "accent")
            self._mouse_command(words[1:])
            return
        if not io.waiting.is_set():
            io.print(BUSY_MESSAGE)
            return
        if not text.strip():
            return
        self.input.reset(append_to_history=True)
        io.transcript.add_text(io.prompt + text, "accent")
        self.main_scroll.to_bottom()
        self._ctrl_c_at = None
        io.submit(text)

    def _mouse_command(self, args: list[str]) -> None:
        if args == []:
            self._set_mouse(not self.ui.mouse)
        elif args == ["on"]:
            self._set_mouse(True)
        elif args == ["off"]:
            self._set_mouse(False)
        else:
            self.io.print("usage: /mouse [on|off]")

    def _set_mouse(self, on: bool) -> None:
        self.ui.mouse = on
        self.io.print(MOUSE_ON if on else MOUSE_OFF)

    def _on_ctrl_c(self) -> None:
        io = self.io
        if io.modal is not None:
            io.answer_approval("n")
            io.cancel_scope.cancel()
            io.print("Interrupting: the tool was denied and the turn stops.")
            return
        if io.asking is not None:
            self.input.reset()
            io.answer_ask(None)
            return
        if not io.waiting.is_set():
            if io.cancel_scope.cancel():
                io.phase = "Interrupting"
            return
        if self.input.text:
            self.input.reset()
            self._ctrl_c_at = None
            return
        now = time.monotonic()
        if self._ctrl_c_at is not None and now - self._ctrl_c_at <= CTRL_C_WINDOW_S:
            self.request_exit("ctrl-c")
            return
        self._ctrl_c_at = now
        io.print(CTRL_C_HINT)

    def _on_ctrl_d(self) -> None:
        if self.io.asking is not None:
            self.io.answer_ask(None)
        elif not self.io.waiting.is_set():
            self.io.print("A turn is running; Ctrl+C interrupts it, then Ctrl+D quits.")
        else:
            self.request_exit("eof")

    def request_exit(self, reason: str) -> None:
        if self.exit_reason is None:
            self.exit_reason = reason
        self.io.shutdown()
        if self._loop:
            self._loop.call_later(FORCE_EXIT_AFTER_S, self._exit_app)

    def _exit_app(self) -> None:
        with contextlib.suppress(Exception):
            self.app.exit()

    def _call_soon(self, fn: Any) -> None:
        with contextlib.suppress(RuntimeError, AttributeError):
            self._loop.call_soon_threadsafe(fn)

    def _write_raw(self, s: str) -> None:
        self.app.output.write_raw(s)
        self.app.output.flush()

    def _write_raw_safe(self, s: str) -> None:
        with contextlib.suppress(Exception):
            self._write_raw(s)

    def handle_signal(self, signum: int, frame: Any = None) -> None:
        reason = "sigterm" if signum == signal.SIGTERM else "sighup"
        self._call_soon(lambda: self.request_exit(reason))

    def _install_signals(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            self._old_signals[sig] = signal.signal(sig, self.handle_signal)

    def _uninstall_signals(self) -> None:
        for sig, old in self._old_signals.items():
            with contextlib.suppress(Exception):
                signal.signal(sig, old)

    def _on_loop_error(self, loop: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        if self.error is None:
            self.error = ("".join(traceback.format_exception(exc)) if exc
                          else str(context.get("message")))
        self.request_exit("error")
        self._exit_app()

    def _pre_run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop.set_exception_handler(self._on_loop_error)
        self.io.on_change = self.app.invalidate
        self.io.post = self._call_soon
        self.io.write_raw = self._write_raw
        self.input.load_history_if_not_yet_loaded()
        self._install_signals()
        self._worker_thread = threading.Thread(target=self._worker, name="cora-repl", daemon=True)
        self._worker_thread.start()

    def _worker(self) -> None:
        try:
            self.code = self.repl.run()
        except BaseException:
            self.error = self.error or traceback.format_exc()
        finally:
            self._call_soon(self._exit_app)

    def run(self) -> int:
        fd = sys.stdin.fileno() if self._pt_input is None and sys.stdin.isatty() else None
        restorer = TerminalRestorer(self._write_raw_safe, fd)
        restorer.install()
        try:
            with contextlib.redirect_stderr(_StderrToTranscript(self.io)):
                self.app.run(pre_run=self._pre_run, handle_sigint=False,
                             set_exception_handler=False)
        except KeyboardInterrupt:
            self.exit_reason = self.exit_reason or "sigint"
        except BaseException:
            if self.error is None:
                self.error = traceback.format_exc()
        finally:
            self._uninstall_signals()
            restorer.restore()
            self.io.shutdown()
            if self._worker_thread is not None:
                self._worker_thread.join(FORCE_EXIT_AFTER_S)
        if self.error is not None:
            sys.stderr.write(self.error if self.error.endswith("\n") else self.error + "\n")
            sys.stderr.flush()
            return 1
        code = EXIT_CODES.get(self.exit_reason or "",
                              self.code if self.code is not None else 0)
        if self.exit_summary and self.exit_reason != "sighup":
            self._write_raw_safe(exit_summary_text(self.repl.session, self.repl.turns))
        return code


def run_tui(opts: ReplOptions, history_path: Path, ui: UiSettings) -> int:
    tio = TuiIO(Transcript(ui.scrollback_blocks), mouse=ui.mouse)
    repl = Repl(tio, opts)
    return TuiApp(repl, tio, history_path=history_path, workdir=repl.workdir,
                  exit_summary=ui.exit_summary).run()
