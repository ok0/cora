from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.config import SaleSettings, load_config
from cora.core.errors import ConfigError
from cora.core.sale import (
    LLMBidGenerator,
    PlanFeatures,
    ReplayPlanner,
    SaleTier,
    TierTable,
    make_bid,
    make_bid_generator,
    plan_features_from_text,
)

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
T2 = TierTable((SaleTier("cheap", 1.0, 0.6), SaleTier("strong", 10.0, 0.9)), source="test")


def test_llm_bids_use_replay_planner():
    p = ReplayPlanner(
        {"cheap": "1. edit a.py", "strong": "1. read a.py\n2. maybe edit a.py\n3. run tests"}
    )
    bids = LLMBidGenerator(p, 20.0).bids("task", T2)
    assert p.calls == [("task", "cheap"), ("task", "strong")]
    assert bids[0] == make_bid(T2.tiers[0], 0, PlanFeatures(1, 1, 1.0, 0.0), 20.0)
    assert bids[1] == make_bid(
        T2.tiers[1], 1, plan_features_from_text(p.plans["strong"]), 20.0
    )


@pytest.mark.parametrize(
    "enabled, bids",
    [(False, "heuristic"), (False, "llm"), (True, "heuristic")],
)
def test_llm_not_used_unless_enabled_and_llm(enabled, bids):
    p = ReplayPlanner({})
    g = make_bid_generator(SaleSettings(enabled=enabled, bids=bids), p)
    assert g.kind == "heuristic"
    g.bids("fix x.py", T2)
    assert p.calls == []


def test_default_repo_config_uses_heuristic():
    p = ReplayPlanner({})
    g = make_bid_generator(load_config(ROOT / "cora.toml").sale, p)
    assert g.kind == "heuristic"
    assert p.calls == []


def test_both_on_uses_llm():
    p = ReplayPlanner({"cheap": "1. read a.py", "strong": "1. read a.py"})
    g = make_bid_generator(SaleSettings(enabled=True, bids="llm"), p)
    assert g.kind == "llm"
    g.bids("task", T2)
    assert len(p.calls) == 2


def test_both_on_without_planner_raises():
    with pytest.raises(ConfigError):
        make_bid_generator(SaleSettings(enabled=True, bids="llm"))


def test_sale_module_has_no_network_or_key_access():
    text = (ROOT / "src/cora/core/sale.py").read_text(encoding="utf-8")
    for needle in ("httpx", "providers", "environ", "OPENROUTER"):
        assert needle not in text

