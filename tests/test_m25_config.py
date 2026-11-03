from __future__ import annotations

import filecmp
import hashlib
from pathlib import Path

import pytest

import m20_trial
from conftest import CFG_TOML
from cora.core.config import AgentSettings, ProjectSettings, load_config, parse_config
from cora.core.errors import ConfigError
from test_project_cli import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
CORA_TOML = ROOT / "cora.toml"
DATA_TOML = ROOT / "src" / "cora" / "data" / "cora.toml"
M20_BASE_SHA256 = "7704ace8db75918f63e2f4df8e6b7d009cabf3d73cc98e0165f6c677abcd883a"
NEW_TOML_LINES = (
    "goal_paths = false",
    "plan_repair_hint = false",
    "tripwire_per_response = false",
)
MODELS = [
    {
        "id": "mock/cheap",
        "provider": "scripted",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    },
    {
        "id": "mock/strong",
        "provider": "scripted",
        "tier": "strong",
        "input_usd_per_mtok": 5.0,
        "output_usd_per_mtok": 10.0,
    },
]


def test_defaults() -> None:
    assert AgentSettings().tripwire_per_response is False
    assert ProjectSettings().goal_paths is False
    assert ProjectSettings().plan_repair_hint is False
    cfg = load_config(CORA_TOML)
    assert cfg.agent.tripwire_per_response is False
    assert cfg.project.goal_paths is False
    assert cfg.project.plan_repair_hint is False
    assert cfg.project.policy_repairs == 1


def test_toml_copies_identical() -> None:
    assert filecmp.cmp(CORA_TOML, DATA_TOML, shallow=False)
    text = CORA_TOML.read_text(encoding="utf-8")
    for line in NEW_TOML_LINES:
        assert line in text
        assert line in DATA_TOML.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "section",
    [
        {"project": {"goal_paths": "yes"}},
        {"project": {"plan_repair_hint": 1}},
        {"agent": {"tripwire_per_response": "x"}},
        {"project": {"goal_pathz": True}},
    ],
)
def test_bad_values_config_error(section) -> None:
    with pytest.raises(ConfigError):
        parse_config({"models": MODELS, **section})


@pytest.mark.parametrize(
    "extra",
    [
        '\n[project]\ngoal_paths = "yes"\n',
        '\n[agent]\ntripwire_per_response = "x"\n',
    ],
)
def test_bad_key_exit_2(tmp_path, extra) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = write_cfg(tmp_path, CFG_TOML + extra)
    result = run_cli(["project", "plan", "g", "-o", str(ws / "p.toml"), *base(ws, cfg)])
    assert result.exit_code == 2


def test_m20_pin_reads_fixture() -> None:
    assert m20_trial.M20_BASE == ROOT / "tests/fixtures/m20/cora-m20-base.toml"
    assert hashlib.sha256(m20_trial.M20_BASE.read_bytes()).hexdigest() == M20_BASE_SHA256
    assert m20_trial.m20_base_text() != CORA_TOML.read_text(encoding="utf-8")
