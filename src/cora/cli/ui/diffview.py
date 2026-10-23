from __future__ import annotations

import re

from rich.text import Text

from cora.cli.ui.theme import Theme

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_lines(diff: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    old = new = old_left = new_left = 0
    for line in diff.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("-"):
                out.append(("remove", f"{old:>4} - {line[1:]}"))
                old += 1
                old_left -= 1
            elif line.startswith("+"):
                out.append(("add", f"{new:>4} + {line[1:]}"))
                new += 1
                new_left -= 1
            elif line.startswith(" ") or line == "":
                out.append(("context", f"{new:>4}   {line[1:]}"))
                old += 1
                new += 1
                old_left -= 1
                new_left -= 1
            elif line.startswith("\\"):
                out.append(("meta", line))
            else:
                out.append(("meta", line))
                old_left = 0
                new_left = 0
        else:
            m = HUNK.match(line)
            if m:
                out.append(("hunk", line))
                old = int(m.group(1))
                new = int(m.group(3))
                old_left = int(m.group(2) or "1")
                new_left = int(m.group(4) or "1")
            elif line.startswith("\\") or line.startswith("..."):
                out.append(("meta", line))
            else:
                out.append(("header", line))
    return out


def diff_text(diff: str, theme: Theme) -> Text:
    styles = {
        "header": theme.hunk,
        "hunk": theme.hunk,
        "add": theme.add,
        "remove": theme.remove,
        "context": "",
        "meta": theme.dim,
    }
    text = Text()
    for i, (kind, body) in enumerate(diff_lines(diff)):
        if i:
            text.append("\n")
        text.append(body, style=styles[kind] or None)
    return text
