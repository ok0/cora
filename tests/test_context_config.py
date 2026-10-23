from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML
from cora.cli.main import app
from cora.core.config import ContextSettings, load_config, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
MODEL = {
    "id": "mock/cheap",
    "provider": "openrouter",
    "tier": "cheap",
    "input_usd_per_mtok": 0.2,
    "output_usd_per_mtok": 0.8,
}


def test_context_defaults_off():
    assert parse_config({"models": [MODEL]}).context == ContextSettings(False, 4000, 500, False)


def test_context_toml_copies_identical_and_off():
    assert (ROOT / "cora.toml").read_bytes() == (ROOT / "src/cora/data/cora.toml").read_bytes()
    data = tomllib.loads((ROOT / "cora.toml").read_text(encoding="utf-8"))
    assert data["context"] == {
        "repo_map": False,
        "repo_map_max_chars": 4000,
        "max_files": 500,
        "dedupe_reads": False,
    }
    assert load_config(ROOT / "cora.toml").context == ContextSettings()


@pytest.mark.parametrize(
    "section",
    [
        {"repo_map": "yes"},
        {"dedupe_reads": 1},
        {"repo_map_max_chars": 0},
        {"repo_map_max_chars": -5},
        {"repo_map_max_chars": True},
        {"repo_map_max_chars": "10"},
        {"max_files": 0},
        {"max_files": 2.5},
        {"unknown": 1},
    ],
)
def test_context_invalid_values(section):
    with pytest.raises(ConfigError, match=r"\[context\]"):
        parse_config({"models": [MODEL], "context": section})


def test_context_section_must_be_table():
    with pytest.raises(ConfigError):
        parse_config({"models": [MODEL], "context": 3})


def test_context_invalid_exits_2(ws, tmp_path):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + "\n[context]\nrepo_map_max_chars = 0\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(path)]
    )
    assert result.exit_code == 2
