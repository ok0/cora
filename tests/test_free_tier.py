from __future__ import annotations

import asyncio

from conftest import act
from cora.core.agent import Agent
from cora.core.budget import BudgetGovernor, BudgetLimits, projected_call_cost
from cora.core.config import ModelSpec, parse_config
from cora.core.metering import CostMeter, projected_cost
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionResponse


def _free_config():
    return parse_config(
        {
            "models": [
                {
                    "id": "free/m",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "free_tier": True,
                },
                {
                    "id": "free/s",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "free_tier": True,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


FREE_SPEC = ModelSpec("free/m", "scripted", "cheap", 1.0, 2.0, free_tier=True)


def test_free_tier_cost_zero():
    response = CompletionResponse("Final Answer: ok", 10, 5, "free/m", cost_usd=0.5)
    meter = CostMeter()
    rec = meter.record(FREE_SPEC, "cheap", "react", response.input_tokens,
                       response.output_tokens, response.cost_usd)
    assert rec.cost_usd == 0.0
    assert rec.price_known is True
    assert rec.cost_source == "free_tier"
    assert meter.total_cost_usd == 0


def test_free_tier_projection_zero():
    assert projected_cost(FREE_SPEC, 10**6, 10**6) == 0.0
    assert projected_call_cost(FREE_SPEC, 10**6, 10**6) == 0.0


def test_cost_cap_never_trips_but_iterations_do(scripted, tmp_path):
    cfg = _free_config()
    gov = BudgetGovernor(BudgetLimits(cost_usd=1e-9, iterations=2), project_cost=True)
    scripted.script.extend([act("list_files", {})] * 5)
    asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto"), governor=gov).run("list"))
    assert gov.tripped == "iterations"

    gov2 = BudgetGovernor(BudgetLimits(cost_usd=1e-9, iterations=2), project_cost=True)
    scripted.script.clear()
    scripted.script.append("Final Answer: ok")
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto"), governor=gov2).run("list"))
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert gov2.tripped is None
