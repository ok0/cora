from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML
from cora.cli.main import app
from cora.core.config import MemorySettings, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
MODEL = {
    "id": "mock/cheap",
    "provider": "openrouter",
    "tier": "cheap",
    "input_usd_per_mtok": 0.2,
    "output_usd_per_mtok": 0.8,
}


def test_memory_defaults():
    memory = parse_config({"models": [MODEL]}).memory
    assert memory.ledger is False
    assert memory.ledger_max_chars == 1500
    assert memory.summarize == "off"


def test_toml_copies_identical_and_hold_keys():
    assert (ROOT / "cora.toml").read_bytes() == (ROOT / "src/cora/data/cora.toml").read_bytes()
    data = tomllib.loads((ROOT / "cora.toml").read_text(encoding="utf-8"))
    expected = {"ledger": False, "ledger_max_chars": 1500, "summarize": "off"}
    assert all(data["memory"][k] == v for k, v in expected.items())


@pytest.mark.parametrize(
    "section",
    [
        {"ledger": "yes"},
        {"ledger": 1},
        {"ledger_max_chars": 0},
        {"ledger_max_chars": 199},
        {"ledger_max_chars": 20001},
        {"ledger_max_chars": True},
        {"ledger_max_chars": "1500"},
        {"summarize": "on"},
        {"summarize": True},
        {"unknown": 1},
    ],
)
def test_memory_invalid_values(section):
    with pytest.raises(ConfigError, match=r"\[memory\]"):
        parse_config({"models": [MODEL], "memory": section})


def test_memory_not_table():
    with pytest.raises(ConfigError):
        parse_config({"models": [MODEL], "memory": 3})


@pytest.mark.parametrize("line", ['summarize = "on"', "bogus = 1", "ledger_max_chars = 0"])
def test_memory_invalid_exits_2(ws, tmp_path, line):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + "\n[memory]\n" + line + "\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(path)]
    )
    assert result.exit_code == 2


def test_summarize_llm_without_ledger_allowed():
    memory = parse_config(
        {"models": [MODEL], "memory": {"summarize": "llm", "ledger": False}}
    ).memory
    assert memory == MemorySettings(ledger=False, summarize="llm")
