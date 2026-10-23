from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

import pytest

from conftest import CFG_TOML, PY, act, run_repl, with_agent, with_decider
from cora.core.agent import Agent
from cora.core.config import (
    DelegationSettings,
    ToolGroupSettings,
    apply_pin,
    parse_config,
)
from cora.core.deciders import HeuristicDecider, ReplayDecider, ReplayStep
from cora.core.metering import CostMeter, format_summary
from cora.core.providers import register_provider
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionResponse
from test_decider_golden import PROMPTS

pytestmark = pytest.mark.usefixtures("no_network")

FAIL = f"{PY} -c \"print('boom'); raise SystemExit(1)\""


@register_provider("decide_mock")
class DecideMock:
    calls: ClassVar[list] = []
    reply: ClassVar[Any] = None

    def __init__(self, s):
        pass

    async def complete(self, req):
        DecideMock.calls.append(req)
        if DecideMock.reply is not None:
            return CompletionResponse(DecideMock.reply(req), 50, 8, req.model)
        e = req.response_format["json_schema"]["schema"]["properties"]["answer"]["enum"]
        return CompletionResponse(json.dumps({"answer": e[0], "confidence": 0.9}), 50, 8, req.model)


@pytest.fixture(autouse=True)
def _reset_decide_mock():
    DecideMock.calls.clear()
    DecideMock.reply = None
    yield
    DecideMock.calls.clear()
    DecideMock.reply = None


def llm_cfg(mock_config):
    return parse_config(
        {
            "models": [
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
                {
                    "id": "mock/decide",
                    "provider": "decide_mock",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
            ],
            "agent": {"approval": "auto"},
            "decider": {"kind": "llm", "model": "mock/decide"},
        }
    )


def no_strong(**agent):
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                }
            ],
            "agent": {"approval": "auto", **agent},
        }
    )


def events(r, kind=None):
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def plain_reasons(reasons: list[str]) -> list[str]:
    return [x for x in reasons if not x.startswith("decider")]


def deleg(cfg, **kw):
    return replace(cfg, delegation=DelegationSettings(enabled=True, **kw))


def replay(cfg, script: dict) -> ReplayDecider:
    return ReplayDecider(HeuristicDecider(cfg), script)


def run(cfg, ws: Path, task: str, *, decider=None, **kw):
    agent = Agent(cfg, ws, ApprovalPolicy("auto"), decider=decider)
    return agent, asyncio.run(agent.run(task, **kw))


def test_agent_heuristic_decider_same_route_and_groups(mock_config, scripted, tmp_path):
    cfg = replace(mock_config, tool_groups=ToolGroupSettings(auto_simple=True))
    dcfg = with_decider(cfg, tier_routing=True, toolgroup=True, sensor_hint=True)
    for prompt in PROMPTS:
        if not prompt:
            continue
        scripted.script[:] = ["Final Answer: ok"]
        before = len(scripted.calls)
        a1, r1 = run(cfg, tmp_path, prompt)
        scripted.script[:] = ["Final Answer: ok"]
        a2, r2 = run(dcfg, tmp_path, prompt)
        assert len(scripted.calls) == before + 2
        assert not events(r1, "decision")
        route1 = events(r1, "route")[0]
        route2 = events(r2, "route")[0]
        assert (route1["tier"], route1["model"], route1["score"], route1["grade"]) == (
            route2["tier"],
            route2["model"],
            route2["score"],
            route2["grade"],
        )
        assert plain_reasons(route1["reasons"]) == plain_reasons(route2["reasons"])
        assert a1.ctx.hidden_groups == a2.ctx.hidden_groups


def test_default_config_no_decision_events(mock_config, scripted, tmp_path):
    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(mock_config, tmp_path, "fix the bug in calc.py")
    assert not events(r, "decision")
    assert not any(
        x.startswith("decider") for e in events(r, "route") for x in e["reasons"]
    )
    assert "decider" not in r.summary


def test_tier_choice_applied(mock_config, scripted, tmp_path):
    cfg = with_decider(mock_config, tier_routing=True)
    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(
        cfg,
        tmp_path,
        "What is 2+2?",
        decider=replay(cfg, {"tier": [ReplayStep(label="strong", confidence=0.9)]}),
    )
    route = events(r, "route")[0]
    assert route["tier"] == "strong"
    assert route["model"] == "mock/strong"
    assert "decider:replay:strong" in route["reasons"]
    assert scripted.calls[0].model == "mock/strong"

    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(
        cfg,
        tmp_path,
        "fix the bug in calc.py",
        decider=replay(cfg, {"tier": [ReplayStep(label="cheap", confidence=0.9)]}),
    )
    assert events(r, "route")[0]["tier"] == "cheap"


def test_pin_wins(mock_config, scripted, tmp_path):
    cfg = apply_pin(with_decider(mock_config, tier_routing=True), "mock/cheap")
    scripted.script[:] = ["Final Answer: ok"]
    rep = replay(cfg, {"tier": [ReplayStep(label="strong", confidence=0.9)]})
    _, r = run(cfg, tmp_path, "What is 2+2?", decider=rep)
    assert events(r, "route")[0]["model"] == "mock/cheap"
    assert ("choice", "tier") not in rep.calls


def test_low_confidence_and_fallback_use_heuristic(mock_config, scripted, tmp_path):
    cfg = with_decider(mock_config, tier_routing=True)
    scripted.script[:] = ["Final Answer: ok"]
    _, base = run(mock_config, tmp_path, "What is 2+2?")
    base_tier = events(base, "route")[0]["tier"]

    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(
        cfg,
        tmp_path,
        "What is 2+2?",
        decider=replay(cfg, {"tier": [ReplayStep(label="strong", confidence=0.3)]}),
    )
    route = events(r, "route")[0]
    assert route["tier"] == base_tier
    assert "decider_ignored:low_confidence" in route["reasons"]

    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(
        cfg,
        tmp_path,
        "What is 2+2?",
        decider=replay(cfg, {"tier": [ReplayStep(fail="timeout")]}),
    )
    route = events(r, "route")[0]
    assert route["tier"] == base_tier
    assert "decider_ignored:timeout" in route["reasons"]


def test_retry_force_wins(mock_config, scripted, tmp_path):
    cfg = with_agent(with_decider(mock_config, tier_routing=True), max_attempts=2)
    scripted.script[:] = ["Final Answer: a", "reflection", "Final Answer: b"]
    rep = replay(cfg, {"tier": [ReplayStep(label="cheap", confidence=0.9)]})
    _, r = run(cfg, tmp_path, "fix the bug in calc.py", decider=rep, check_command=FAIL)
    routes = events(r, "route")
    assert routes[0]["tier"] == "cheap"
    assert routes[1]["tier"] == "strong"
    assert "forced:strong" in routes[1]["reasons"]
    assert not any(x.startswith("decider:") for x in routes[1]["reasons"])
    assert rep.calls.count(("choice", "tier")) == 1


def test_tripwire_escalation_preserved(mock_config, scripted, tmp_path):
    cfg = with_agent(with_decider(mock_config, tier_routing=True), tripwire=True)
    items = [act("read_file", {"path": "missing.txt"}) for _ in range(3)]
    items.append("Final Answer: ok")
    scripted.script[:] = items
    rep = replay(cfg, {"tier": [ReplayStep(label="cheap", confidence=1.0)]})
    _, r = run(cfg, tmp_path, "hi", decider=rep)
    last = events(r, "route")[-1]
    assert last["reasons"] == ["tripwire_escalation"]
    assert last["tier"] == "strong"
    assert scripted.calls[3].model == "mock/strong"


def test_toolgroup_noul(mock_config, scripted, tmp_path):
    cfg = replace(mock_config, tool_groups=ToolGroupSettings(auto_simple=True))
    dcfg = with_decider(cfg, toolgroup=True)

    scripted.script[:] = ["Final Answer: ok"]
    agent, _ = run(cfg, tmp_path, "say hi")
    assert "git" in agent.ctx.hidden_groups

    scripted.script[:] = ["Final Answer: ok"]
    rep = replay(dcfg, {"group:git": [ReplayStep(p_yes=0.95, confidence=0.95)]})
    agent, _ = run(dcfg, tmp_path, "say hi", decider=rep)
    assert "git" not in agent.ctx.hidden_groups
    assert "web" in agent.ctx.hidden_groups

    scripted.script[:] = ["Final Answer: ok"]
    rep = replay(dcfg, {"group:git": [ReplayStep(fail="provider_error")]})
    agent, _ = run(dcfg, tmp_path, "say hi", decider=rep)
    assert "git" in agent.ctx.hidden_groups

    scripted.script[:] = ["Final Answer: ok"]
    rep = replay(
        dcfg, {"group:git": [ReplayStep(p_yes=0.0, confidence=1.0)]}
    )
    agent, _ = run(dcfg, tmp_path, "show the git log", decider=rep)
    assert "git" in agent.ctx.hidden_groups


def test_complete_hint_cannot_change_sensor(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, sensor_max_retries=1)
    scripted.script[:] = ["Final Answer: a"] * 5
    _, r0 = run(cfg, tmp_path, "hi", check_command=FAIL, sensor=True)
    calls0 = len(scripted.calls)

    scripted.calls.clear()
    scripted.script[:] = ["Final Answer: a"] * 5
    dcfg = with_decider(cfg, sensor_hint=True)
    rep = replay(dcfg, {"complete": [ReplayStep(p_yes=0.99, confidence=0.99)] * 5})
    _, r1 = run(dcfg, tmp_path, "hi", decider=rep, check_command=FAIL, sensor=True)

    assert r0.stop_reason == StopReason.CHECK_FAILED
    assert r1.stop_reason == StopReason.CHECK_FAILED
    assert [e["ok"] for e in events(r0, "check")] == [e["ok"] for e in events(r1, "check")]
    assert calls0 == len(scripted.calls)
    assert any(e["question"] == "complete" for e in events(r1, "decision"))


def test_stuck_hint_cannot_change_tripwire(mock_config, scripted, tmp_path):
    cfg = no_strong(tripwire=True)
    items = [act("read_file", {"path": "missing.txt"}) for _ in range(3)]
    scripted.script[:] = list(items)
    _, r0 = run(cfg, tmp_path, "hi")

    scripted.script[:] = list(items)
    dcfg = with_decider(cfg, sensor_hint=True)
    rep = replay(dcfg, {"stuck": [ReplayStep(p_yes=0.0, confidence=1.0)] * 5})
    _, r1 = run(dcfg, tmp_path, "hi", decider=rep)

    assert r0.stop_reason == StopReason.TRIPWIRE
    assert r1.stop_reason == StopReason.TRIPWIRE
    assert any(e["question"] == "stuck" for e in events(r1, "decision"))


def test_delegation_unchanged_with_decider(mock_config, scripted, tmp_path):
    cfg = deleg(mock_config, max_per_session=1)
    script = [
        act("delegate", {"task": "list the files and summarize"}),
        act("list_files", {}),
        "Final Answer: SUBSUMMARY two files",
        act("delegate", {"task": "again"}),
        "Final Answer: done",
    ]

    def delegate_trace(events_list):
        return [e["type"] for e in events_list if e["type"] in ("delegate_start", "delegate_end")]

    scripted.script[:] = list(script)
    base_events: list[dict] = []
    base = asyncio.run(
        Agent(cfg, tmp_path, ApprovalPolicy("auto"), on_event=base_events.append).run("main task")
    )
    base_calls = len(scripted.calls)

    scripted.calls.clear()
    scripted.script[:] = list(script)
    dcfg = with_decider(cfg, tier_routing=True, toolgroup=True, sensor_hint=True)
    rep = replay(dcfg, {})
    dec_events: list[dict] = []
    dec = asyncio.run(
        Agent(
            dcfg, tmp_path, ApprovalPolicy("auto"), decider=rep, on_event=dec_events.append
        ).run("main task")
    )

    assert dec.session.delegations == base.session.delegations
    assert dec.summary["delegated"]["calls"] == base.summary["delegated"]["calls"]
    assert len(scripted.calls) == base_calls
    assert delegate_trace(dec_events) == delegate_trace(base_events)
    assert {m for m, _ in rep.calls} <= {"choice", "noul"}


def test_llm_decider_records_and_report(mock_config, tmp_path, scripted):
    cfg = with_decider(
        replace(llm_cfg(mock_config), tool_groups=ToolGroupSettings(auto_simple=True)),
        tier_routing=True,
        toolgroup=True,
        sensor_hint=True,
    )
    scripted.script[:] = ["Final Answer: ok"]
    _, r = run(cfg, tmp_path, "ZEBRA-7731 say hi")
    recs = events(r, "decision")
    assert [e["question"] for e in recs] == [
        "tier",
        "group:git",
        "group:web",
        "group:plan-todo",
        "complete",
    ]
    fields = {
        "kind",
        "question",
        "input_hash",
        "output",
        "confidence",
        "cost_usd",
        "latency_ms",
        "fallback_used",
        "decider",
        "model",
        "reason",
    }
    for e in recs:
        assert fields <= set(e)
        assert all(e[f] is not None for f in fields)
        assert e["model"] == "mock/decide"
    assert all("ZEBRA-7731" not in json.dumps(e) for e in recs)
    assert {rec.purpose for rec in CostMeter.from_list(r.session.meter).records} == {
        "react",
        "decide",
    }
    assert len(DecideMock.calls) == 5
    assert len(scripted.calls) == 1
    assert r.summary["decider"]["decisions"] == 5
    assert r.summary["decider"]["fallbacks"] == 0
    assert r.summary["decider"]["cost_usd"] > 0
    assert "decider: decisions=5 fallbacks=0" in format_summary(r.summary)


def test_repl_decider_command(ws, tmp_path, scripted):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + "\n[decider]\ntier_routing = true\n", encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(
        ws, path, ["/decider", "ZEBRA-7731 hi", "/decider", "/decider x", "/exit"]
    )
    assert "decider: heuristic" in out
    assert "No decisions yet" in out
    assert "choice tier -> cheap" in out
    assert "usage: /decider" in out
    assert "ZEBRA" not in out.split("recent decisions", 1)[1]

    plain = tmp_path / "plain.toml"
    plain.write_text(CFG_TOML, encoding="utf-8")
    out = run_repl(ws, plain, ["/decider", "/exit"])
    assert "all uses are off" in out
