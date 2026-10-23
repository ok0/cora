from __future__ import annotations

from dataclasses import fields
from io import StringIO

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.styles import Style
from rich.cells import cell_len
from rich.style import Style as RichStyle
from rich.text import Text

from cora.cli.io import TerminalIO
from cora.cli.ui.state import UiState
from cora.cli.ui.theme import (
    ASCII_GLYPHS,
    THEMES,
    UNICODE_GLYPHS,
    Glyphs,
    Theme,
    color_enabled,
    make_console,
    unicode_supported,
)
from cora.core.config import UI_THEMES, UiSettings

PT_FIELDS = ["pt_marker", "pt_mode", "pt_dim"]
STYLE_FIELDS = [f.name for f in fields(Theme) if f.name not in ("name", *PT_FIELDS)]


def test_all_themes_load() -> None:
    assert tuple(THEMES) == UI_THEMES
    for name in UI_THEMES:
        assert THEMES[name].name == name


def test_rich_styles_parse() -> None:
    for theme in THEMES.values():
        for name in STYLE_FIELDS:
            RichStyle.parse(getattr(theme, name))


def test_prompt_toolkit_styles_parse() -> None:
    for theme in THEMES.values():
        for name in PT_FIELDS:
            Style.from_dict({"x": getattr(theme, name)}).get_attrs_for_style_str("class:x")


def test_mono_has_no_styles() -> None:
    mono = THEMES["mono"]
    for name in STYLE_FIELDS + PT_FIELDS:
        assert getattr(mono, name) == ""


def test_ascii_glyphs_are_ascii() -> None:
    for f in fields(Glyphs):
        if f.name == "ascii":
            continue
        ascii_value = getattr(ASCII_GLYPHS, f.name)
        unicode_value = getattr(UNICODE_GLYPHS, f.name)
        assert all(ord(c) < 128 for c in ascii_value)
        if any(ord(c) >= 128 for c in unicode_value):
            assert ascii_value != unicode_value


def test_color_enabled() -> None:
    assert color_enabled("always", isatty=False, env={}) is True
    assert color_enabled("always", isatty=True, env={"NO_COLOR": "1"}) is False
    assert color_enabled("auto", isatty=False, env={}) is False
    assert color_enabled("auto", isatty=True, env={}) is True
    assert color_enabled("never", isatty=True, env={}) is False


def test_unicode_supported() -> None:
    assert unicode_supported("UTF-8") is True
    assert unicode_supported("ascii") is False
    assert unicode_supported(None) is False


def test_make_console_without_color_emits_no_escapes() -> None:
    buf = StringIO()
    make_console(color=False, force_terminal=True, file=buf).print(Text("x", style="bold red"))
    assert "\x1b" not in buf.getvalue()
    assert cell_len(buf.getvalue().strip()) == 1


def test_terminal_attach_no_color(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    with create_pipe_input() as pipe:
        io = TerminalIO(tmp_path / "hist", ["/help"], pt_input=pipe, pt_output=DummyOutput())
        assert io.attach(UiState.from_settings(UiSettings(color="always"))) is True
        assert io.console.color_system is None
        assert io._session.color_depth == ColorDepth.MONOCHROME
