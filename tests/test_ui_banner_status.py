from __future__ import annotations

from io import StringIO

from rich.cells import cell_len
from rich.console import Console

from cora.cli.ui.banner import Banner, BannerInfo
from cora.cli.ui.state import UiState
from cora.cli.ui.statusline import context_percent, statusline, with_interrupt_hint
from cora.cli.ui.theme import ASCII_GLYPHS, THEMES, UNICODE_GLYPHS

INFO = BannerInfo(
    "0.1.0",
    "/tmp/project",
    ("cheap=mock/cheap", "strong=mock/strong"),
    "ask",
    "CORA.md",
    "main...origin/main (2 changed)",
)


def _render(width: int, glyphs=UNICODE_GLYPHS) -> str:
    buf = StringIO()
    con = Console(file=buf, width=width, color_system=None)
    con.print(Banner(INFO, THEMES["default"], glyphs))
    return buf.getvalue()


def test_banner_wide_has_fields_and_single_tip() -> None:
    out = _render(100)
    for field in (
        "CORA 0.1.0",
        "/tmp/project",
        "cheap=mock/cheap",
        "approval: ask",
        "guide: CORA.md",
        "git: main",
    ):
        assert field in out
    assert out.count("Esc+Enter") == 1
    assert "╭" in out


def test_banner_narrow_keeps_fields() -> None:
    out = _render(50)
    for field in ("CORA 0.1.0", "/tmp/project", "cheap=mock/cheap", "approval: ask", "git: main"):
        assert field in out
    assert all(not (0x2500 <= ord(ch) <= 0x257F) for ch in out)


def test_banner_ascii_is_ascii() -> None:
    out = _render(100, ASCII_GLYPHS)
    assert all(ord(ch) < 128 for ch in out)


def test_statusline_contents() -> None:
    ui = UiState(
        THEMES["default"],
        approval="ask",
        model="cheap:mock/cheap",
        groups=("git", "web"),
        plan=True,
        cost_usd=0.0123,
        context_pct=3.2,
        started=0.0,
    )
    text = statusline(ui, 100, now=125.0)
    for part in (
        "approval:ask",
        "cheap:mock/cheap",
        "$0.0123",
        "ctx 3%",
        "plan",
        "tools:git,web",
        "2:05",
        "todo:on",
    ):
        assert part in text
    for width in (100, 50):
        line = statusline(ui, width, now=125.0)
        assert "\n" not in line
        assert cell_len(line) <= width


def test_statusline_keeps_approval_when_narrow() -> None:
    ui = UiState(
        THEMES["default"],
        approval="ask",
        model="cheap:google/gemini-2.5-flash-lite",
        started=0.0,
    )
    assert "approval:ask" in statusline(ui, 50, now=1.0)


def test_statusline_mono_placeholders() -> None:
    text = statusline(UiState(THEMES["mono"]), 50, now=1.0)
    assert "model:-" in text
    assert "$-" in text
    assert "ctx -" in text


def test_context_percent_and_hint() -> None:
    assert context_percent(None, 1000) is None
    assert context_percent(10, 0) is None
    assert context_percent(500, 1000) == 50.0
    assert with_interrupt_hint("Thinking") == "Thinking (Ctrl+C to interrupt)"
