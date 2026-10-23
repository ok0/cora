from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from conftest import CFG_TOML
from cora.core.config import UiSettings, load_config, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
MINIMAL = tomllib.loads(CFG_TOML)


def test_ui_defaults() -> None:
    assert parse_config(MINIMAL).ui == UiSettings("default", False, "auto")


def test_ui_new_key_defaults() -> None:
    ui = UiSettings()
    assert ui.tui is True
    assert ui.mouse is True
    assert ui.exit_summary is True
    assert ui.scrollback_blocks == 5000


@pytest.mark.parametrize("path", [ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml"])
def test_shipped_tomls_use_ui_defaults(path: Path) -> None:
    assert load_config(path).ui == UiSettings()


@pytest.mark.parametrize(
    ("ui", "message"),
    [
        ({"theme": "nope"}, "invalid [ui].theme"),
        ({"color": "rainbow"}, "invalid [ui].color"),
        ({"ascii": "yes"}, "invalid [ui].ascii"),
        ({"tui": "yes"}, "invalid [ui].tui"),
        ({"mouse": 1}, "invalid [ui].mouse"),
        ({"exit_summary": "no"}, "invalid [ui].exit_summary"),
        ({"scrollback_blocks": 10}, "invalid [ui].scrollback_blocks"),
        ({"scrollback_blocks": True}, "invalid [ui].scrollback_blocks"),
        ({"bogus": 1}, "invalid [ui] section"),
    ],
)
def test_invalid_ui_values_are_config_errors(ui: dict, message: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(message)):
        parse_config({**MINIMAL, "ui": ui})
