from __future__ import annotations

from io import StringIO

from rich.console import Console

from cora.cli.ui.diffview import diff_lines, diff_text
from cora.cli.ui.theme import THEMES
from cora.core.tools import unified_diff


def _diff() -> str:
    return unified_diff("a.txt", "hello\nx\n", "bye\nx\n")


def test_diff_lines_classified() -> None:
    assert diff_lines(_diff()) == [
        ("header", "--- a/a.txt"),
        ("header", "+++ b/a.txt"),
        ("hunk", "@@ -1,2 +1,2 @@"),
        ("remove", "   1 - hello"),
        ("add", "   1 + bye"),
        ("context", "   2   x"),
    ]


def test_diff_color_on() -> None:
    buf = StringIO()
    con = Console(file=buf, color_system="truecolor", force_terminal=True)
    con.print(diff_text(_diff(), THEMES["default"]))
    lines = buf.getvalue().split("\n")
    plus = next(ln for ln in lines if "+ bye" in ln)
    minus = next(ln for ln in lines if "- hello" in ln)
    assert "\x1b[" in plus and "\x1b[" in minus
    assert plus.split("+ bye")[0] != minus.split("- hello")[0]
    assert THEMES["default"].add != THEMES["default"].remove


def test_diff_color_off() -> None:
    buf = StringIO()
    con = Console(file=buf, color_system=None)
    con.print(diff_text(_diff(), THEMES["default"]))
    out = buf.getvalue()
    assert "   1 - hello" in out
    assert "   1 + bye" in out
    assert "\x1b" not in out


def test_truncated_marker_is_meta() -> None:
    kinds = diff_lines("@@ -1 +1 @@\n-a\n+b\n... (diff truncated)")
    assert kinds[-1] == ("meta", "... (diff truncated)")
