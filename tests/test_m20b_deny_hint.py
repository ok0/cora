"""M20b deny-hint tests.

Each denial case is taken from the recorded M20 artifacts under
tests/fixtures/m20/artifacts. The command is replayed as a tool call, except
case 5 (`default`, `test -f` chain), which was recorded only as a sensor check.
Replaying it as a run_shell tool call is the synthetic route (D2).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import act, with_agent
from cora.core.agent import Agent
from cora.core.config import DelegationSettings
from cora.core.policy import RULE_HINTS, PolicyGate, PolicySettings, hint_for
from cora.core.tools import ApprovalPolicy, ToolContext
from cora.core.tools.base import Workspace
from cora.core.tools.builtin import default_tools
from cora.core.tools.registry import ToolRegistry

ART = Path(__file__).parent / "fixtures" / "m20" / "artifacts"
M20_PATH = re.compile(r"<M20>/\S*?/ws")
OBS = "Observation: "


def _fail(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("approval prompt must not be called in policy mode")


def _fail_review(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("review prompt must not be called in policy mode")


def artifact_event(rel: str, line: int) -> dict:
    return json.loads((ART / rel).read_text(encoding="utf-8").splitlines()[line - 1])


def artifact_rule(rel: str, line: int) -> str:
    ev = artifact_event(rel, line)
    if "rule" in ev:
        return ev["rule"]
    if ev["type"] == "check":
        return ev["policy"]
    m = re.search(r"\(([\w:.-]+)\)|rule ([\w:.-]+),", ev["output_head"])
    assert m, f"no rule recorded in {rel}:{line}"
    return m.group(1) or m.group(2)


def _sub(value: Any, ws: Path) -> Any:
    if isinstance(value, str):
        return M20_PATH.sub(str(ws), value)
    return value


def artifact_call(rel: str, line: int, ws: Path) -> tuple[str, dict]:
    ev = artifact_event(rel, line)
    if ev["type"] == "tool_call":
        args = {k: _sub(v, ws) for k, v in json.loads(ev["args"]).items()}
        return ev["tool"], args
    if ev["type"] == "policy_decision":
        return "run_shell", {"command": _sub(ev["args"], ws)}
    assert ev["type"] == "check"
    return "run_shell", {"command": _sub(ev["command"], ws)}


CASES = [
    (
        "confine:cd",
        "v2/e2e_h03-r1/sessions/20261025-224751-214c62/events.jsonl",
        20,
        "confine:cd",
        "deny",
    ),
    (
        "confine:one-liner",
        "v2/e2e_h01-r1/sessions/20261025-220907-07c65a/events.jsonl",
        41,
        "confine:one-liner",
        "deny",
    ),
    (
        "confine:parse",
        "v2/e2e_h03-r1/sessions/20261025-224751-214c62/events.jsonl",
        35,
        "confine:parse",
        "deny",
    ),
    (
        "default:delete",
        "v2/e2e_h03-r1/sessions/20261025-224751-214c62/events.jsonl",
        70,
        "default:delete",
        "ask",
    ),
    (
        "default",
        "v2/e2e_n08-r0/sessions/20261025-225819-9e8303/events.jsonl",
        24,
        "default",
        "deny",
    ),
    (
        "confine:python-module",
        "p2/e2e_h01-r1/sessions/20261023-212725-94bafc/events.jsonl",
        67,
        "confine:python-module",
        "deny",
    ),
]
CASE_IDS = [c[0] for c in CASES]


def _expected_counts(decision: str) -> tuple[int, int]:
    return (1, 0) if decision == "deny" else (0, 1)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_registry_denial_adds_hint(case, tmp_path):
    _cid, rel, line, rule, decision = case
    assert artifact_rule(rel, line) == rule
    ws = tmp_path / "ws"
    ws.mkdir()
    tool, args = artifact_call(rel, line, ws)
    ctx = ToolContext(
        Workspace(ws),
        ApprovalPolicy("policy", ask=_fail, review=_fail_review),
        gate=PolicyGate(PolicySettings(), ws),
    )
    v = ctx.gate.verdict(tool, args, "policy")
    assert v is not None
    assert (v.rule, v.decision) == (rule, decision)
    assert v.blocked
    res = asyncio.run(ToolRegistry(default_tools()).execute(tool, args, ctx))
    assert res.ok is False
    assert res.output == v.message + "\nHint: " + hint_for(v)
    assert res.output.count("\nHint: ") == 1
    assert hint_for(v) == f"{RULE_HINTS[rule].text} {RULE_HINTS[rule].remedy}"
    assert ctx.gate.tally.deny + ctx.gate.tally.ask_denied == 1
    if decision == "deny":
        assert ctx.gate.tally.deny == 1
    else:
        assert (ctx.gate.tally.ask, ctx.gate.tally.ask_denied) == (1, 1)


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_agent_observation_and_events(case, mock_config, tmp_path, scripted):
    _cid, rel, line, rule, decision = case
    ws = tmp_path / "ws"
    ws.mkdir()
    tool, args = artifact_call(rel, line, ws)
    v = PolicyGate(PolicySettings(), ws).verdict(tool, args, "policy")
    assert v is not None and (v.rule, v.decision) == (rule, decision)
    scripted.script[:] = [act(tool, args), "Final Answer: done"]
    events: list[dict] = []
    agent = Agent(
        mock_config,
        ws,
        ApprovalPolicy("policy", ask=_fail, review=_fail_review),
        on_event=events.append,
    )
    r = asyncio.run(agent.run("t"))
    assert any(
        m.content == OBS + v.message + "\nHint: " + hint_for(v) for m in scripted.calls[1].messages
    )
    decisions = [e for e in events if e["type"] == "policy_decision"]
    assert len(decisions) == 1
    assert (
        decisions[0]["decision"],
        decisions[0]["rule"],
        decisions[0]["resolved"],
        decisions[0]["mode"],
    ) == (decision, rule, "deny", "policy")
    pol = r.summary["policy"]
    assert (pol["deny"], pol["ask_resolved_deny"]) == _expected_counts(decision)
    assert pol["source"] == "builtin"


def test_allowed_call_has_no_hint(mock_config, tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    scripted.script[:] = [act("run_shell", {"command": "ls"}), "Final Answer: done"]
    agent = Agent(mock_config, ws, ApprovalPolicy("policy", ask=_fail, review=_fail_review))
    asyncio.run(agent.run("t"))
    obs = [m.content for m in scripted.calls[1].messages if m.content.startswith(OBS)]
    assert len(obs) == 1
    assert "Hint:" not in obs[0]
    assert not obs[0].startswith(OBS + "denied")


def test_prompt_approved_call_has_no_hint(mock_config, tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "x.txt").write_text("x\n", encoding="utf-8")
    cfg = with_agent(mock_config, approval="ask")
    scripted.script[:] = [act("delete_file", {"path": "x.txt"}), "Final Answer: done"]
    asyncio.run(Agent(cfg, ws, ApprovalPolicy("ask", ask=lambda _a: True)).run("t"))
    assert not (ws / "x.txt").exists()
    obs = [m.content for m in scripted.calls[1].messages if m.content.startswith(OBS)]
    assert len(obs) == 1
    assert "Hint:" not in obs[0]


def test_user_denial_unchanged(mock_config, tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "x.txt").write_text("x\n", encoding="utf-8")
    scripted.script[:] = [act("delete_file", {"path": "x.txt"}), "Final Answer: done"]
    asyncio.run(Agent(mock_config, ws, ApprovalPolicy("deny")).run("t"))
    assert (ws / "x.txt").exists()
    obs = [m.content for m in scripted.calls[1].messages if m.content.startswith(OBS)]
    assert len(obs) == 1
    assert "denied by user: approval required for delete_file" in obs[0]
    assert "Hint:" not in obs[0]


def test_subagent_denial_gets_hint(mock_config, tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = dataclasses.replace(mock_config, delegation=DelegationSettings(enabled=True))
    rel, line = CASES[0][1], CASES[0][2]
    tool, args = artifact_call(rel, line, ws)
    v = PolicyGate(PolicySettings(), ws).verdict(tool, args, "policy")
    assert v is not None
    scripted.script[:] = [
        act("delegate", {"task": "t"}),
        act(tool, args),
        "Final Answer: s",
        "Final Answer: m",
    ]
    agent = Agent(cfg, ws, ApprovalPolicy("policy", ask=_fail, review=_fail_review))
    asyncio.run(agent.run("main"))
    text = scripted.calls[2].messages[-1].content
    assert text.count(v.message + "\nHint: " + hint_for(v)) == 1
