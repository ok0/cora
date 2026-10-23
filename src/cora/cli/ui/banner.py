from __future__ import annotations

from dataclasses import dataclass

from rich import box
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.panel import Panel
from rich.text import Text

from cora.cli.ui.theme import Glyphs, Theme

NARROW_WIDTH = 60
BANNER_TIPS = (
    "Tip: end a line with \\ or press Esc+Enter for a new line; /help lists commands.",
    "Shift+Tab cycles approval, Ctrl+T toggles the TODO view, Ctrl+C interrupts a turn, "
    "Ctrl+D quits.",
)


@dataclass(frozen=True)
class BannerInfo:
    version: str
    workdir: str
    models: tuple[str, ...]
    approval: str
    guide: str | None
    git: str | None


def banner_lines(info: BannerInfo, glyphs: Glyphs, *, narrow: bool) -> list[str]:
    return [
        f"CORA {info.version} {glyphs.dot} Cost-Oriented Routing Agent",
        f"workdir: {info.workdir}",
        "models: " + "  ".join(info.models),
        f"approval: {info.approval}",
        f"guide: {info.guide}" if info.guide else "guide: none (run /init to create CORA.md)",
        *([f"git: {info.git}"] if info.git else []),
        "",
        *(BANNER_TIPS[:1] if narrow else BANNER_TIPS),
    ]


def banner_renderable(
    info: BannerInfo, theme: Theme, glyphs: Glyphs, width: int
) -> RenderableType:
    narrow = width < NARROW_WIDTH
    lines = banner_lines(info, glyphs, narrow=narrow)
    tip_count = len(BANNER_TIPS[:1] if narrow else BANNER_TIPS)
    tip_start = len(lines) - tip_count
    text = Text()
    for i, line in enumerate(lines):
        if i:
            text.append("\n")
        if i == 0:
            style = theme.accent or None
        elif i >= tip_start:
            style = theme.dim or None
        else:
            style = None
        text.append(line, style=style)
    if narrow:
        return text
    return Panel(
        text,
        box=box.ASCII if glyphs.ascii else box.ROUNDED,
        border_style=theme.accent or "none",
        expand=False,
        padding=(0, 1),
    )


@dataclass(frozen=True)
class Banner:
    info: BannerInfo
    theme: Theme
    glyphs: Glyphs

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield banner_renderable(self.info, self.theme, self.glyphs, options.max_width)
