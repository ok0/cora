from __future__ import annotations

import filecmp
import re
import tomllib
from pathlib import Path

import pytest

from conftest import CFG_TOML, ScriptedProvider
from cora.core.config import (
    ConfigError,
    RecordSettings,
    effective_record_settings,
    load_config,
    parse_config,
)
from cora.core.providers import ProviderPool
from cora.core.types import CompletionRequest
from test_headless import base, doc, run_cli

ROOT = Path(__file__).resolve().parents[1]


def test_default_off():
    cfg = parse_config(tomllib.loads(CFG_TOML))
    assert cfg.record == RecordSettings("off", ".cora/recordings")
    assert isinstance(ProviderPool(cfg).get("scripted"), ScriptedProvider)


def test_repo_toml_record_off():
    assert load_config(ROOT / "cora.toml").record.mode == "off"


def test_toml_copies_identical():
    assert filecmp.cmp(ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml", shallow=False)


def test_env_overrides_config():
    cfg = parse_config(tomllib.loads(CFG_TOML + '\n[record]\nmode = "record"\ndir = "a"\n')).record
    assert cfg == RecordSettings("record", "a")
    assert effective_record_settings(
        cfg, {"CORA_RECORD_MODE": "replay", "CORA_RECORD_DIR": "/x/b"}
    ) == RecordSettings("replay", "/x/b")
    assert effective_record_settings(cfg, {}) == RecordSettings("record", "a")


def test_invalid_config_mode():
    with pytest.raises(ConfigError, match=re.escape("[record].mode")):
        parse_config(tomllib.loads(CFG_TOML + '\n[record]\nmode = "sometimes"\n'))
    with pytest.raises(ConfigError, match=re.escape("[record].dir")):
        parse_config(tomllib.loads(CFG_TOML + "\n[record]\ndir = 3\n"))


def test_invalid_env_mode_exit_2(scripted, ws, cfg_file, monkeypatch):
    monkeypatch.setenv("CORA_RECORD_MODE", "bogus")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 2
    assert "CORA_RECORD_MODE" in d["errors"][0]


def test_off_request_bodies_unchanged(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: 42")
    d = doc(run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)]))
    assert d["stop_reason"] == "final_answer"
    assert type(scripted.calls[0]) is CompletionRequest
    assert not (ws / ".cora" / "recordings").exists()
