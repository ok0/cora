from __future__ import annotations

from io import StringIO

from rich.cells import cell_len
from rich.console import Console

from cora.cli.ui.theme import ASCII_GLYPHS, THEMES, UNICODE_GLYPHS
from cora.cli.ui.toolview import ToolCallView, args_summary, collapse


def _lines(view: ToolCallView, width: int = 100) -> list[str]:
    buf = StringIO()
    Console(file=buf, width=width, color_system=None).print(view)
    return [ln.rstrip() for ln in buf.getvalue().split("\n") if ln.strip()]


def test_ok_result_head_and_body() -> None:
    view = ToolCallView("read_file", "src/x.py", True, "a\nb", THEMES["default"], UNICODE_GLYPHS)
    assert _lines(view) == ["● read_file(src/x.py)", "  ⎿  a", "     b"]


def test_long_args_are_truncated() -> None:
    view = ToolCallView("read_file", "x" * 300, True, "ok", THEMES["default"], UNICODE_GLYPHS)
    first = _lines(view, 50)[0]
    assert first.endswith("…)")
    assert cell_len(first) <= 50


def test_long_output_is_collapsed_with_footer() -> None:
    output = "\n".join(f"l{i}" for i in range(25))
    view = ToolCallView("run_shell", "", True, output, THEMES["default"], UNICODE_GLYPHS)
    text = "\n".join(_lines(view))
    assert "… +22 lines (/expand)" in text
    assert "l2" in text
    assert "l3" not in text


def test_exactly_ten_lines_not_collapsed() -> None:
    output = "\n".join(map(str, range(10)))
    view = ToolCallView("run_shell", "", True, output, THEMES["default"], UNICODE_GLYPHS)
    assert "/expand" not in "\n".join(_lines(view))
    assert collapse(output)[1] == 0


def test_long_result_line_fits_width() -> None:
    view = ToolCallView("read_file", "a.txt", True, "y" * 200, THEMES["default"], UNICODE_GLYPHS)
    for line in _lines(view, 50):
        assert cell_len(line) <= 50


def test_error_result_rendering() -> None:
    view = ToolCallView(
        "edit_file", "", False, "denied by user\nmore", THEMES["default"], UNICODE_GLYPHS
    )
    lines = _lines(view)
    assert lines[0].startswith("✗ edit_file(")
    assert lines[1] == "  ⎿  error: denied by user"
    ascii_view = ToolCallView(
        "edit_file", "", False, "denied by user\nmore", THEMES["default"], ASCII_GLYPHS
    )
    ascii_lines = _lines(ascii_view)
    assert ascii_lines[0].startswith("! edit_file(")
    assert ascii_lines[1].startswith("  |_  error:")
    ok_view = ToolCallView("edit_file", "", True, "x", THEMES["default"], UNICODE_GLYPHS)
    assert _lines(ok_view)[0].startswith("●")
    assert not lines[0].startswith("●")


def test_args_summary() -> None:
    assert args_summary("", "{}") == ""
    assert args_summary("a.txt", "{...}") == "a.txt"
