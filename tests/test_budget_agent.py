from __future__ import annotations

import asyncio

from conftest import act, with_agent
from cora.core.agent import Agent
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.observability import read_events
from cora.core.state import Session, StopReason
from cora.core.tools import ApprovalPolicy


def test_default_governor_matches_config(mock_config, tmp_path):
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    assert agent.governor.limits == BudgetLimits(0.5, 30, None, None)
    assert agent.governor.project_cost is False


def test_tool_calls_trip(mock_config, tmp_path, scripted):
    scripted.script.extend([act("list_files", {})] * 10)
    governor = BudgetGovernor(BudgetLimits(0.5, 30, None, 2), project_cost=True)
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), governor=governor)
    r = asyncio.run(agent.run("list"))
    assert r.stop_reason == StopReason.BUDGET_EXCEEDED
    assert r.session.budget["tripped"] == "tool_calls"
    assert r.session.budget["used"]["tool_calls"] == 2
    assert len(scripted.calls) == 3
    trips = [e for e in read_events(r.log_path) if e["type"] == "budget_trip"]
    assert len(trips) == 1


def test_iteration_trip_keeps_legacy_reason(mock_config, tmp_path, scripted):
    scripted.script.extend([act("list_files", {})] * 10)
    cfg = with_agent(mock_config, max_iterations=3)
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("list"))
    assert r.stop_reason == StopReason.MAX_ITERATIONS
    assert len(scripted.calls) == 3
    assert r.session.budget["tripped"] == "iterations"


def test_budget_warning_event_once(mock_config, tmp_path, scripted):
    scripted.script.extend([act("list_files", {})] * 10)
    cfg = with_agent(mock_config, max_iterations=5)
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("list"))
    warnings = [e for e in read_events(r.log_path) if e["type"] == "budget_warning"]
    assert len(warnings) == 1
    assert warnings[0]["cap"] == "iterations"


def test_request_stop_after_inflight_call(mock_config, tmp_path, scripted):
    scripted.script.extend([act("list_files", {})] * 5)
    holder: dict[str, Agent] = {}

    def on_event(ev: dict) -> None:
        if ev["type"] == "llm_call" and "agent" in holder:
            holder["agent"].request_stop()

    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), on_event=on_event)
    holder["agent"] = agent
    r = asyncio.run(agent.run("list"))
    assert r.stop_reason == StopReason.INTERRUPTED
    assert len(scripted.calls) == 1
    session_file = agent.sessions.dir_for(r.session.id) / "session.json"
    assert session_file.exists()
    assert '"stop_reason": "interrupted"' in session_file.read_text(encoding="utf-8")


def test_old_session_without_budget_loads():
    data = Session(id="a", task="t").to_dict()
    data.pop("budget", None)
    loaded = Session.from_dict(data)
    assert loaded.budget is None


def test_resume_seeds_cost(mock_config, tmp_path, scripted):
    scripted.script.append("Final Answer: one")
    first = asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("first"))
    cost = first.session.budget["used"]["cost_usd"]
    assert cost > 0
    calls_before = len(scripted.calls)
    governor = BudgetGovernor(BudgetLimits(cost_usd=cost + 1e-9), project_cost=True)
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), governor=governor)
    r = asyncio.run(agent.run("again", session=first.session))
    assert r.stop_reason == StopReason.COST_LIMIT
    assert len(scripted.calls) == calls_before
