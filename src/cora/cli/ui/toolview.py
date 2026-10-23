from __future__ import annotations

from dataclasses import dataclass

from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

from cora.cli.ui.statusline import fit
from cora.cli.ui.theme import Glyphs, Theme

COLLAPSE_LINES = 10
PREVIEW_LINES = 3


def args_summary(target: str, args_json: str) -> str:
    return target or ("" if args_json in ("", "{}") else args_json)


def _one_line(s: str) -> str:
    return s.replace("\r", "").replace("\t", "    ").replace("\n", " ")


def collapse(
    output: str, max_lines: int = COLLAPSE_LINES, preview: int = PREVIEW_LINES
) -> tuple[list[str], int]:
    lines = [ln.replace("\r", "").replace("\t", "    ") for ln in output.rstrip("\n").split("\n")]
    if len(lines) <= max_lines:
        return lines, 0
    return lines[:preview], len(lines) - preview


def tool_call_text(
    name: str,
    args: str,
    ok: bool,
    output: str,
    theme: Theme,
    glyphs: Glyphs,
    width: int,
    *,
    max_lines: int = COLLAPSE_LINES,
    head_only: bool = False,
) -> Text:
    width = max(width, 20)
    mark = glyphs.tool if ok else glyphs.tool_error
    text = Text()
    text.append(mark, style=(theme.tool if ok else theme.error) or None)
    text.append(f" {name}", style="bold")
    head_args = fit(
        _one_line(args), width - cell_len(f"{mark} {name}()"), glyphs.ellipsis
    )
    text.append(f"({head_args})", style=theme.dim or None)
    if head_only:
        return text
    prefix = f"  {glyphs.result}  "
    pad = " " * cell_len(prefix)
    avail = width - cell_len(prefix)
    if not ok:
        first = _one_line(output.split("\n", 1)[0]).strip()
        rows = [(f"error: {first}", theme.error)]
    elif not output.strip():
        rows = [("(no output)", theme.dim)]
    else:
        shown, hidden = collapse(output, max_lines)
        rows = [(ln, theme.dim) for ln in shown]
        if hidden:
            rows.append((f"{glyphs.ellipsis} +{hidden} lines (/expand)", theme.dim))
    for i, (row, style) in enumerate(rows):
        text.append("\n")
        text.append(prefix if i == 0 else pad, style=theme.dim or None)
        text.append(fit(row, avail, glyphs.ellipsis), style=style or None)
    return text


@dataclass(frozen=True)
class ToolCallView:
    name: str
    args: str
    ok: bool
    output: str
    theme: Theme
    glyphs: Glyphs
    head_only: bool = False
    max_lines: int = COLLAPSE_LINES

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield tool_call_text(
            self.name,
            self.args,
            self.ok,
            self.output,
            self.theme,
            self.glyphs,
            options.max_width,
            max_lines=self.max_lines,
            head_only=self.head_only,
        )
