from __future__ import annotations

import pytest

from cora.core.config import (
    ModelOverride,
    ModelSpec,
    apply_model_override,
    effective_protocol,
    parse_config,
)
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter, projected_cost

MODELS = [
    {
        "id": "a",
        "provider": "scripted",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    },
    {
        "id": "b",
        "provider": "scripted",
        "tier": "strong",
        "input_usd_per_mtok": 5.0,
        "output_usd_per_mtok": 10.0,
    },
]


def _minimal(**extra) -> dict:
    return {"models": [dict(m) for m in MODELS], **extra}


def test_default_agent_tool_protocol_is_react():
    assert parse_config(_minimal()).agent.tool_protocol == "react"


def test_invalid_agent_tool_protocol_rejected():
    with pytest.raises(ConfigError, match="tool_protocol"):
        parse_config(_minimal(agent={"tool_protocol": "xml"}))


def test_invalid_model_tool_protocol_rejected():
    data = _minimal()
    data["models"][0]["tool_protocol"] = "bogus"
    with pytest.raises(ConfigError):
        parse_config(data)


def test_non_bool_supports_tools_rejected():
    data = _minimal()
    data["models"][0]["supports_tools"] = "yes"
    with pytest.raises(ConfigError):
        parse_config(data)


def _spec(**kwargs) -> ModelSpec:
    base = dict(id="m", provider="p", tier="cheap", input_usd_per_mtok=1.0, output_usd_per_mtok=2.0)
    base.update(kwargs)
    return ModelSpec(**base)


def test_effective_protocol_resolution():
    react_cfg = parse_config(_minimal())
    assert effective_protocol(react_cfg, _spec(tool_protocol="native")) == "native"
    assert effective_protocol(react_cfg, _spec()) == "react"

    auto_cfg = parse_config(_minimal(agent={"tool_protocol": "auto"}))
    assert effective_protocol(auto_cfg, _spec(supports_tools=True)) == "native"
    assert effective_protocol(auto_cfg, _spec(supports_tools=False)) == "react"
    assert effective_protocol(auto_cfg, _spec(supports_tools=None)) == "react"

    native_cfg = parse_config(_minimal(agent={"tool_protocol": "native"}))
    assert effective_protocol(native_cfg, _spec(tool_protocol="react")) == "react"


def test_apply_model_override_keeps_tool_fields():
    data = _minimal()
    data["models"][0]["tool_protocol"] = "native"
    data["models"][0]["supports_tools"] = True
    cfg = apply_model_override(parse_config(data), ModelOverride("cheap", "a"), "user")
    spec = next(m for m in cfg.models if m.tier == "cheap")
    assert spec.supports_tools is True
    assert spec.tool_protocol == "native"


def test_bench_section_parsing():
    with pytest.raises(ConfigError):
        parse_config(_minimal(bench={"models": ["a"], "protocols": ["react", "xml"]}))
    cfg = parse_config(_minimal(bench={"models": ["a"]}))
    assert cfg.bench.models == ("a",)


def test_projected_cost_unknown_price_uses_conservative_rate():
    spec = ModelSpec("u", "p", "cheap", None, None)
    assert projected_cost(spec, 1000, 1000) == pytest.approx(0.09)


def test_provider_reported_cost_is_recorded():
    meter = CostMeter()
    spec = _spec(id="m", tier="cheap")
    rec = meter.record(spec, "cheap", "react", 10, 5, cost_usd=0.5)
    assert rec.cost_usd == 0.5
    assert rec.cost_source == "provider_usage"
    assert meter.summary()["provider_cost_calls"] == 1
