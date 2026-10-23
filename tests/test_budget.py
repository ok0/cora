from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.budget import BudgetGovernor, BudgetLimits, BudgetUsage, projected_call_cost
from cora.core.config import (
    AgentSettings,
    HeadlessSettings,
    ModelSpec,
    load_config,
    parse_config,
)
from cora.core.errors import ConfigError
from cora.core.metering import projected_cost

REPO = Path(__file__).resolve().parents[1]


def _model_dict() -> dict:
    return {
        "id": "m1",
        "provider": "openrouter",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    }


def test_limits_clamp():
    got = BudgetLimits(1.0, 50, None, 10).clamp(BudgetLimits(0.3, 30, 900.0, None))
    assert got == BudgetLimits(0.3, 30, 900.0, 10)


def test_from_agent_zero_is_unlimited():
    assert BudgetLimits.from_agent(AgentSettings()) == BudgetLimits(0.5, 30, None, None)


def test_seed_prior_usage():
    g = BudgetGovernor(
        BudgetLimits(cost_usd=1.0),
        seed=BudgetUsage(cost_usd=0.9, tool_calls=3),
    )
    assert g.usage().cost_usd == 0.9
    assert g.usage().tool_calls == 3
    assert g.check_model_call(0.2) == "cost"


def test_unpriced_projects_zero():
    unpriced = ModelSpec("u", "p", "cheap", None, None)
    priced = ModelSpec("p", "p", "cheap", 1.0, 2.0)
    assert projected_call_cost(unpriced, 10_000, 1024) == 0.0
    assert projected_call_cost(priced, 10_000, 1024) == projected_cost(priced, 10_000, 1024)


def test_one_warning_per_cap():
    g = BudgetGovernor(BudgetLimits(iterations=5, tool_calls=5))
    for _ in range(5):
        g.add_iteration()
    for _ in range(5):
        g.add_tool_calls(1)
    assert g.drain_warnings() == [("iterations", 4, 5), ("tool_calls", 4, 5)]
    assert g.drain_warnings() == []
    assert g.to_dict()["warned"] is True


def test_no_warning_below_fraction():
    g = BudgetGovernor(BudgetLimits(iterations=5))
    for _ in range(3):
        g.add_iteration()
    assert g.drain_warnings() == []
    assert g.to_dict()["warned"] is False


def test_trip_recorded_once_and_sticky():
    g = BudgetGovernor(BudgetLimits(tool_calls=1))
    assert g.check_tool_call() is None
    g.add_tool_calls(1, name="x")
    assert g.check_tool_call() == "tool_calls"
    assert g.check_tool_call() == "tool_calls"
    assert g.check_model_call() == "tool_calls"
    assert g.tripped == "tool_calls"
    assert g.tool_counts == {"x": 1}


def test_wall_with_injected_clock():
    ticks = iter([0, 100, 200, 300])
    g = BudgetGovernor(BudgetLimits(wall_s=250), clock=lambda: next(ticks))
    assert g.check_model_call() is None
    assert g.check_model_call() is None
    assert g.check_model_call() == "wall"
    warnings = g.drain_warnings()
    assert warnings == [("wall", 200, 250)]


def test_project_cost_flag():
    g = BudgetGovernor(BudgetLimits(cost_usd=1.0), project_cost=False)
    assert g.check_model_call(5.0) is None
    g2 = BudgetGovernor(BudgetLimits(cost_usd=1.0), project_cost=True)
    assert g2.check_model_call(5.0) == "cost"


def test_iterations_per_attempt():
    g = BudgetGovernor(BudgetLimits(iterations=2))
    g.add_iteration()
    g.add_iteration()
    assert g.check_model_call() == "iterations"

    g2 = BudgetGovernor(BudgetLimits(iterations=2))
    g2.add_iteration()
    g2.add_iteration()
    g2.new_attempt()
    assert g2.check_model_call() is None
    assert g2.usage().iterations == 2
    assert g2.check_model_call(iterations=False) is None


def test_to_dict_shape():
    g = BudgetGovernor(BudgetLimits(cost_usd=1.0))
    d = g.to_dict()
    assert set(d) == {"limits", "used", "tripped", "warned"}
    keys = {"cost_usd", "iterations", "wall_s", "tool_calls"}
    assert set(d["limits"]) == keys
    assert set(d["used"]) == keys
    assert d["limits"]["iterations"] is None
    assert d["limits"]["wall_s"] is None
    assert d["limits"]["tool_calls"] is None


@pytest.mark.parametrize("bad", [0, 1.5, -0.1])
def test_invalid_warn_fraction(bad):
    with pytest.raises(ValueError):
        BudgetGovernor(BudgetLimits(), warn_fraction=bad)


def test_config_defaults():
    cfg = parse_config({"models": [_model_dict()]})
    assert cfg.agent.max_wall_s == 0
    assert cfg.agent.max_tool_calls == 0
    assert cfg.agent.budget_warn_fraction == 0.8
    assert cfg.headless == HeadlessSettings(900, 200)
    shipped = load_config(REPO / "cora.toml")
    assert shipped.agent.max_wall_s == 0
    assert shipped.agent.max_tool_calls == 0
    assert shipped.agent.budget_warn_fraction == 0.8
    assert shipped.headless == HeadlessSettings(900, 200)


@pytest.mark.parametrize(
    "section, value, key",
    [
        ("agent", {"max_wall_s": -1}, "max_wall_s"),
        ("agent", {"max_tool_calls": "x"}, "max_tool_calls"),
        ("agent", {"budget_warn_fraction": 0}, "budget_warn_fraction"),
        ("agent", {"budget_warn_fraction": 1.5}, "budget_warn_fraction"),
        ("agent", {"budget_warn_fraction": -0.1}, "budget_warn_fraction"),
        ("agent", {"max_cost_usd": -1}, "max_cost_usd"),
        ("agent", {"max_iterations": -1}, "max_iterations"),
        ("headless", {"max_wall_s": -5}, "max_wall_s"),
        ("headless", {"bogus": 1}, "headless"),
    ],
)
def test_config_invalid_values(section, value, key):
    data = {"models": [_model_dict()], section: value}
    with pytest.raises(ConfigError, match=key):
        parse_config(data)
