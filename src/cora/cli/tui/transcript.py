from __future__ import annotations

import dataclasses
import io
import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prompt_toolkit.formatted_text import ANSI, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from rich.console import Console, RenderableType
from rich.markdown import Markdown
from rich.text import Text

from cora.cli.ui.diffview import diff_text
from cora.cli.ui.theme import THEMES, Theme
from cora.cli.ui.toolview import ToolCallView

OMITTED = "… earlier output omitted (scrollback limit: [ui] scrollback_blocks)"
WHEEL_LINES = 3
_ids = itertools.count(1)

@dataclass
class Block:
    kind: str                 # "text" | "markdown" | "diff" | "rich"
    text: str = ""
    style_key: str = ""       # "" | "warn" | "dim" | "accent"
    renderable: Any = None
    id: int = field(default_factory=lambda: next(_ids))
    version: int = 0

def _style(theme: Theme, key: str) -> str:
    return {"warn": theme.warn, "dim": theme.dim, "accent": theme.accent}.get(key, "") or ""

def block_renderable(b: Block, theme: Theme, expanded: bool) -> RenderableType:
    if b.kind == "markdown":
        return Markdown(b.text)
    if b.kind == "diff":
        return diff_text(b.text, theme)
    if b.kind == "rich":
        r = b.renderable
        if dataclasses.is_dataclass(r) and not isinstance(r, type) and hasattr(r, "theme"):
            r = dataclasses.replace(r, theme=theme)
        if expanded and isinstance(r, ToolCallView) and not r.head_only:
            r = dataclasses.replace(r, max_lines=10**9)
        return r
    return Text(b.text, style=_style(theme, b.style_key))

def _merge(line: StyleAndTextTuples) -> StyleAndTextTuples:
    out: list[tuple[str, str]] = []
    for frag in line:
        style, text = frag[0], frag[1]
        if not text:
            continue
        if out and out[-1][0] == style:
            out[-1] = (style, out[-1][1] + text)
        else:
            out.append((style, text))
    return out

def render_lines(
    renderable: RenderableType, width: int, *, color: bool
) -> list[StyleAndTextTuples]:
    buf = io.StringIO()
    console = Console(file=buf, width=max(1, width), force_terminal=True,
                      color_system="256" if color else None, highlight=False,
                      legacy_windows=False, soft_wrap=False)
    console.print(renderable)
    text = buf.getvalue()
    if text.endswith("\n"):
        text = text[:-1]
    return [_merge(line) for line in split_lines(to_formatted_text(ANSI(text)))]

class Transcript:
    def __init__(self, max_blocks: int = 5000) -> None:
        self.max_blocks = max_blocks
        self._blocks: list[Block] = []
        self._lock = threading.Lock()
        self._stream: Block | None = None
        self._cache: dict[tuple, list[StyleAndTextTuples]] = {}
        self._flat: dict[bool, tuple[tuple, list[StyleAndTextTuples]]] = {}
        self.dropped = 0
        self.version = 0

    def _add(self, block: Block) -> Block:
        with self._lock:
            self._blocks.append(block)
            extra = len(self._blocks) - self.max_blocks
            if extra > 0:
                del self._blocks[:extra]
                self.dropped += extra
            self.version += 1
        return block

    def add_text(self, text: str, style_key: str = "") -> None:
        self._add(Block("text", text, style_key))

    def add_markdown(self, text: str) -> None:
        self._add(Block("markdown", text))

    def add_diff(self, text: str) -> None:
        self._add(Block("diff", text))

    def add_rich(self, renderable: Any) -> None:
        self._add(Block("rich", renderable=renderable))

    def stream_start(self) -> None:
        self._stream = self._add(Block("markdown", ""))

    def stream_delta(self, text: str) -> None:
        if self._stream is None:
            self.stream_start()
        with self._lock:
            self._stream.text += text
            self._stream.version += 1
            self.version += 1

    def stream_end(self) -> None:
        self._stream = None

    def lines(self, width: int, theme: Theme, *, color: bool,
              expanded: bool = False) -> list[StyleAndTextTuples]:
        key = (self.version, width, theme.name, color)
        cached = self._flat.get(expanded)
        if cached is not None and cached[0] == key:
            return cached[1]
        with self._lock:
            snap = [(b, b.version) for b in self._blocks]
            dropped = self.dropped
        out: list[StyleAndTextTuples] = [[("class:hint", OMITTED)]] if dropped else []
        live = set()
        for b, ver in snap:
            k = (b.id, ver, width, theme.name, color, expanded)
            live.add(k)
            ls = self._cache.get(k)
            if ls is None:
                ls = render_lines(block_renderable(b, theme, expanded), width, color=color)
                self._cache[k] = ls
            out.extend(ls)
        self._cache = {k: v for k, v in self._cache.items() if k in live or k[5] != expanded}
        self._flat[expanded] = (key, out)
        return out

    def plain_text(self, width: int = 100, *, expanded: bool = False) -> str:
        mono = THEMES["mono"]
        return "\n".join("".join(f[1] for f in line)
                         for line in self.lines(width, mono, color=False, expanded=expanded))

class ScrollState:
    def __init__(self) -> None:
        self.offset = 0          # lines from the bottom; 0 = follow
        self.height = 1
        self.unseen = False
        self._total: int | None = None
        self._width: int | None = None

    @property
    def following(self) -> bool:
        return self.offset == 0

    def window(self, total: int, height: int, width: int) -> tuple[int, int]:
        if (self.offset > 0 and self._total is not None and width == self._width
                and total > self._total):
            self.offset += total - self._total
            self.unseen = True
        self._total, self._width, self.height = total, width, max(1, height)
        self.offset = max(0, min(self.offset, max(0, total - self.height)))
        if self.offset == 0:
            self.unseen = False
        top = max(0, total - self.height - self.offset)
        return top, min(total, top + self.height)

    def scroll(self, n: int) -> None:
        self.offset = max(0, self.offset + n)

    def to_top(self) -> None:
        self.offset = 10**9

    def to_bottom(self) -> None:
        self.offset = 0
        self.unseen = False

class TranscriptControl(UIControl):
    def __init__(
        self, get_lines: Callable[[int], list[StyleAndTextTuples]], scroll: ScrollState
    ) -> None:
        self._get_lines, self.scroll = get_lines, scroll

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        lines = self._get_lines(width)
        top, bottom = self.scroll.window(len(lines), height, width)
        visible = lines[top:bottom]
        return UIContent(get_line=lambda i: visible[i] if 0 <= i < len(visible) else [],
                         line_count=max(1, len(visible)), show_cursor=False)

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.scroll.scroll(WHEEL_LINES)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.scroll.scroll(-WHEEL_LINES)
            return None
        return NotImplemented
