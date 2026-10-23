from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

from cora.core.config import ProjectSettings, load_config, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]

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


def test_project_defaults(mock_config) -> None:
    assert mock_config.project == ProjectSettings()
    assert mock_config.project.gate_retries == 1
    assert mock_config.project.max_milestones == 8
    assert mock_config.project.condition_timeout_s == 60
    assert mock_config.project.condition_output_chars == 2000


def test_shipped_toml_identical_and_parses() -> None:
    assert filecmp.cmp(ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml", shallow=False)
    assert load_config(ROOT / "cora.toml").project == ProjectSettings()


def test_project_override() -> None:
    cfg = parse_config({"models": MODELS, "project": {"gate_retries": 0, "max_milestones": 3}})
    assert cfg.project.gate_retries == 0
    assert cfg.project.max_milestones == 3


@pytest.mark.parametrize(
    ("project", "match"),
    [
        ({"gate_retries": -1}, "gate_retries"),
        ({"gate_retries": True}, "gate_retries"),
        ({"max_milestones": 0}, "max_milestones"),
        ({"condition_timeout_s": 1.5}, "condition_timeout_s"),
        ({"condition_output_chars": 0}, "condition_output_chars"),
        ({"bogus": 1}, r"invalid \[project\] section"),
        (3, "must be a table"),
    ],
)
def test_invalid_project_values(project, match) -> None:
    with pytest.raises(ConfigError, match=match):
        parse_config({"models": MODELS, "project": project})
