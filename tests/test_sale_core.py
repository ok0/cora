from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.errors import ConfigError
from cora.core.sale import (
    HeuristicBidGenerator,
    PlanFeatures,
    SaleTier,
    TierTable,
    choose_tier,
    difficulty,
    load_tier_table,
    make_bid,
    parse_tier_table,
    plan_features_from_text,
    plan_size,
    record_attempt,
    run_escalation,
    start_escalation,
)

pytestmark = pytest.mark.usefixtures("no_network")

T2 = TierTable((SaleTier("cheap", 1.0, 0.6), SaleTier("strong", 10.0, 0.9)), source="test")
T3 = TierTable(
    (SaleTier("cheap", 1.0, 0.6), SaleTier("mid", 4.0, 0.8), SaleTier("strong", 10.0, 0.9)),
    source="test",
)
A = PlanFeatures(1, 1, 0.0, 0.0)
B = PlanFeatures(8, 5, 0.6, 0.6)
C = PlanFeatures(4, 2, 0.5, 0.5)
Z = PlanFeatures(0, 0, 0.0, 0.0)
gen = HeuristicBidGenerator(20.0)


def test_builtin_table_is_measured():
    t = load_tier_table()
    assert t.names == ("cheap", "strong")
    assert t.placeholder is False
    assert t.tiers[0].cost < t.tiers[1].cost
    for x in t.tiers:
        assert 0 <= x.solve_rate <= 1
    assert t.source == "built-in sale_tiers.toml"


@pytest.mark.parametrize(
    "features, expected, d, size",
    [
        (A, [(1.05, 0.51, 9.15), (10.5, 0.8775, 7.05)], 0.15, 1.05),
        (B, [(1.4, 0.0, -1.4), (14.0, 0.75, 1.0)], 1.0, 1.4),
        (C, [(1.2, 0.21, 3.0), (12.0, 0.8025, 4.05)], 0.65, 1.2),
        (Z, [(1.0, 0.6, 11.0), (10.0, 0.9, 8.0)], 0.0, 1.0),
    ],
    ids=["A", "B", "C", "Z"],
)
def test_bids_match_hand_calculation(features, expected, d, size):
    bids = gen.bids("", T2, features)
    assert len(bids) == 2
    for bid, (cost, success, value) in zip(bids, expected, strict=True):
        assert bid.estimated_cost == pytest.approx(cost)
        assert bid.expected_success == pytest.approx(success)
        assert bid.value == pytest.approx(value)
    assert bids[0].difficulty == pytest.approx(d)
    assert bids[0].size == pytest.approx(size)


def test_bids_are_deterministic():
    first = gen.bids("x", T2, C)
    assert gen.bids("x", T2, C) == first
    assert gen.bids("x", T2, C) == first
    t = T2.tiers[0]
    assert make_bid(t, 0, C, 20.0) == make_bid(t, 0, C, 20.0)


def test_plan_features_from_text():
    assert plan_features_from_text("1. read a.py\n2. maybe edit a.py\n3. run tests") == (
        PlanFeatures(3, 1, 2 / 3, 1 / 3)
    )
    assert plan_features_from_text("") == PlanFeatures(0, 0, 0.0, 0.0)
    text = "1. read a.py\n2. maybe edit a.py\n3. run tests"
    assert plan_features_from_text(text) == plan_features_from_text(text)


def test_plan_features_validation():
    with pytest.raises(ValueError):
        PlanFeatures(-1, 0)
    with pytest.raises(ValueError):
        PlanFeatures(1, 0, 1.5)
    with pytest.raises(ValueError):
        PlanFeatures(True, 0)
    with pytest.raises(ValueError):
        PlanFeatures.from_mapping({"steps": 1})


def test_difficulty_and_size_helpers():
    assert difficulty(A) == pytest.approx(0.15)
    assert plan_size(A) == pytest.approx(1.05)


def test_router_max_value_within_budget():
    assert choose_tier(gen.bids("", T3, C), 20.0).tier == "mid"
    decision = choose_tier(gen.bids("", T3, C), 4.0)
    assert decision.tier == "cheap"
    assert decision.over_budget is False


def test_router_tie_prefers_cheaper():
    t = TierTable((SaleTier("a", 1.0, 0.5), SaleTier("b", 2.0, 0.75)), source="test")
    bids = HeuristicBidGenerator(4.0).bids("", t, Z)
    assert bids[0].value == pytest.approx(1.0)
    assert bids[1].value == pytest.approx(1.0)
    assert choose_tier(bids, 100.0).tier == "a"


def test_router_all_over_budget():
    decision = choose_tier(gen.bids("", T2, A), 0.5)
    assert decision.tier == "cheap"
    assert decision.over_budget is True
    assert decision.reason == "all_over_budget"


def test_router_simple_cheap_complex_strong():
    assert choose_tier(gen.bids("", T2, A), 20.0).tier == "cheap"
    assert choose_tier(gen.bids("", T2, B), 20.0).tier == "strong"


def test_escalation_climbs_one_tier_at_a_time():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=100)
    end = run_escalation(start, [False, False, False])
    assert end.attempts == ("cheap", "mid", "strong")
    assert end.status == "failed"
    assert end.reason == "top_tier_failed"
    assert end.spent == pytest.approx(15.0)
    assert end.escalations == 2


def test_escalation_pass_ends_immediately():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=100)
    end = run_escalation(start, [True, False, False])
    assert end.status == "passed"
    assert end.attempts == ("cheap",)
    assert end.spent == pytest.approx(1.0)


def test_escalation_fail_then_pass():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=100)
    end = run_escalation(start, [False, True])
    assert end.status == "passed"
    assert end.attempts == ("cheap", "mid")
    assert end.spent == pytest.approx(5.0)


def test_escalation_max_escalations():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=1, budget_cap=100)
    end = run_escalation(start, [False, False, False])
    assert end.status == "failed"
    assert end.reason == "max_escalations"
    assert end.attempts == ("cheap", "mid")


def test_escalation_budget_cap():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=6)
    end = run_escalation(start, [False, False])
    assert end.status == "failed"
    assert end.reason == "budget_cap"
    assert end.attempts == ("cheap", "mid")
    assert end.spent == pytest.approx(5.0)


def test_escalation_explicit_cost():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=100)
    end = record_attempt(start, passed=False, cost=2.5)
    assert end.spent == pytest.approx(2.5)
    assert end.tier == "mid"
    assert end.status == "running"


def test_escalation_starting_at_top():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "strong", max_escalations=5, budget_cap=100)
    end = run_escalation(start, [False])
    assert end.reason == "top_tier_failed"


def test_record_attempt_on_finished_state_raises():
    bids = gen.bids("", T3, Z)
    start = start_escalation(bids, "cheap", max_escalations=5, budget_cap=100)
    done = run_escalation(start, [True])
    with pytest.raises(ValueError):
        record_attempt(done, passed=False)


_GOOD_TIERS = [
    {"name": "cheap", "cost": 1.0, "solve_rate": 0.6},
    {"name": "strong", "cost": 10.0, "solve_rate": 0.9},
]


@pytest.mark.parametrize(
    "data",
    [
        {"tiers": [_GOOD_TIERS[0]]},
        {
            "tiers": [
                {"name": "a", "cost": 2.0, "solve_rate": 0.5},
                {"name": "b", "cost": 1.0, "solve_rate": 0.5},
            ]
        },
        {"tiers": [{"name": "a", "cost": 1.0, "solve_rate": 1.5}, _GOOD_TIERS[1]]},
        {"tiers": [{**_GOOD_TIERS[0], "extra": 1}, _GOOD_TIERS[1]]},
        {"tiers": _GOOD_TIERS, "foo": 1},
        {"tiers": _GOOD_TIERS, "placeholder": "yes"},
        {"tiers": [_GOOD_TIERS[0], {**_GOOD_TIERS[1], "name": "cheap"}]},
    ],
    ids=[
        "one_tier",
        "cost_not_increasing",
        "solve_rate_out_of_range",
        "extra_tier_key",
        "unknown_top_key",
        "placeholder_not_bool",
        "duplicate_names",
    ],
)
def test_tier_table_validation(data):
    with pytest.raises(ConfigError):
        parse_tier_table(data, "t")


def test_load_missing_tier_table(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_tier_table(tmp_path / "none.toml")
