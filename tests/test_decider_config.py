from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from cora.core.config import DeciderSettings, load_config, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = [ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml"]
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


def _parse(decider: dict[str, Any]):
    return parse_config({"models": MODELS, "decider": decider})


def test_defaults_without_section(mock_config):
    assert mock_config.decider == DeciderSettings()
    assert mock_config.decider.kind == "heuristic"
    assert not mock_config.decider.tier_routing
    assert not mock_config.decider.toolgroup
    assert not mock_config.decider.sensor_hint


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_shipped_tomls_have_section_defaults(path):
    assert "[decider]" in path.read_text(encoding="utf-8")
    assert load_config(path).decider == DeciderSettings()


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ({"kind": "jev"}, "[decider].kind"),
        ({"model": "nope/x"}, "[decider].model"),
        ({"timeout_s": 0}, "timeout_s"),
        ({"timeout_s": "5"}, "timeout_s"),
        ({"max_cost_per_decision": -1}, "max_cost_per_decision"),
        ({"min_confidence": 1.5}, "min_confidence"),
        ({"tier_routing": "yes"}, "tier_routing"),
        ({"bogus": 1}, "invalid [decider] section"),
    ],
)
def test_invalid_values(raw, match):
    with pytest.raises(ConfigError, match=re.escape(match)):
        _parse(raw)


@pytest.mark.parametrize("model", ["strong", "mock/strong"])
def test_model_accepts_tier_or_id(model):
    assert _parse({"model": model}).decider.model == model
