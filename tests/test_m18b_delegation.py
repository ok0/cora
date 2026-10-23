from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import act, native, tc
from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.config import ToolGroupSettings, apply_pin, load_config
from cora.core.metering import format_summary
from cora.core.outcome import OUTCOME_KEYS
from cora.core.policy import PolicyGate, PolicySettings, Rule
from cora.core.prompts import DELEGATE_NUDGE
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionResponse
from explore_mock import ExploreMock, explore, explore_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_mock():
    ExploreMock.reset()


def _task_of(req):
    first = req.messages[1].content if len(req.messages) > 1 else ""
    return first[len("Task: ") :] if first.startswith("Task: ") else None


def sub_reqs():
    return [r for r in ExploreMock.calls if _task_of(r) in ExploreMock.subs]


def main_reqs():
    return [r for r in ExploreMock.calls if _task_of(r) not in ExploreMock.subs]


def go(cfg, tmp_path, policy=None, policy_gate=None):
    events: list[dict] = []
    agent = Agent(
        cfg,
        tmp_path,
        policy or ApprovalPolicy("auto"),
        on_event=events.append,
        policy_gate=policy_gate,
    )
    r = asyncio.run(agent.run("main task"))
    return r, events


def doc(result) -> dict:
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    d = json.loads(result.stdout)
    assert set(d) == set(OUTCOME_KEYS)
    assert d["exit_code"] == result.exit_code
    return d


def session_json(ws: Path, sid: str) -> dict:
    return json.loads((ws / ".cora" / "sessions" / sid / "session.json").read_text("utf-8"))


def test_bogus_mode_counts_attempt(tmp_path):
    ExploreMock.main = [act("delegate", {"task": "x", "mode": "bogus"}), "Final Answer: done"]
    r, _ = go(explore_config(), tmp_path)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["invocations"] == 0
    assert r.summary["delegated"]["attempts_unparsed"] == 0
    assert r.session.delegation_stats["attempts"] == 1
    assert "attempts=1 attempts_unparsed=0" in format_summary(r.summary)


def test_policy_denied_counts_attempt(tmp_path):
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    gate = PolicyGate(
        PolicySettings(rules=(Rule("u", "deny", ("delegate",), index=1),)), tmp_path
    )
    r, _ = go(explore_config(), tmp_path, ApprovalPolicy("policy"), policy_gate=gate)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["invocations"] == 0
    assert not [q for q in ExploreMock.calls if _task_of(q) == "qa"]


def test_cap_refusal_counts_attempt(tmp_path):
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    r, _ = go(explore_config({"explore_max_calls": 0}), tmp_path)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["invocations"] == 0
    assert r.summary["delegated"]["refused"] == 1


def test_unparsed_delegate_line_counts(tmp_path):
    ExploreMock.main = ["Thought: x\nAction: delegate\n", "Final Answer: done"]
    r, _ = go(explore_config(), tmp_path)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["attempts_unparsed"] == 1
    assert r.summary["delegated"]["invocations"] == 0


def test_unparsed_without_delegate_line(tmp_path):
    ExploreMock.main = ["Thought: x\nAction: read_file\nAction Input: {bad", "Final Answer: done"]
    r, _ = go(explore_config(), tmp_path)
    assert r.summary["delegated"].get("attempts", 0) == 0
    assert r.session.delegation_stats["attempts"] == 0
    assert r.session.delegation_stats["attempts_unparsed"] == 0


def test_unparsed_truncated_counts_once(tmp_path):
    ExploreMock.main = [
        CompletionResponse(
            'Thought: x\nAction: delegate\nAction Input: {"task": "a',
            10,
            10,
            "mock/cheap",
            finish_reason="length",
        ),
        "Final Answer: done",
    ]
    r, _ = go(explore_config(), tmp_path)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["attempts_unparsed"] == 1


def test_started_delegate_counts_attempt_and_invocation(tmp_path):
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    r, _ = go(explore_config(), tmp_path)
    assert r.summary["delegated"]["attempts"] == 1
    assert r.summary["delegated"]["invocations"] == 1


def test_attempts_not_counted_when_delegation_off(tmp_path):
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    r, _ = go(explore_config(enabled=False), tmp_path)
    assert r.session.delegation_stats.get("attempts", 0) == 0
    assert "invocations" not in r.summary["delegated"]


def test_headless_session_has_attempts(scripted, ws, cfg_file):
    scripted.script.extend([act("delegate", {"task": "x", "mode": "bogus"}), "Final Answer: done"])
    result = CliRunner().invoke(
        app,
        ["run", "q", "--headless", "--json", "--delegate", "-w", str(ws), "-c", str(cfg_file)],
    )
    d = doc(result)
    stored = session_json(ws, d["session_id"])
    assert stored["delegation_stats"]["attempts"] == 1
    assert stored["delegation_stats"]["attempts_unparsed"] == 0


def test_nudge_on_main_only(tmp_path):
    cfg = explore_config({"nudge": True})
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    go(cfg, tmp_path)
    mains = main_reqs()
    assert mains
    assert all(r.messages[0].content.endswith(DELEGATE_NUDGE) for r in mains)
    assert all(DELEGATE_NUDGE.strip() not in r.messages[0].content for r in sub_reqs())

    ExploreMock.reset()
    native_cfg = explore_config({"nudge": True}, agent={"tool_protocol": "native"})
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [
        native(tc("delegate", {"task": "qa", "mode": "explore"})),
        native(text="done"),
    ]
    go(native_cfg, tmp_path)
    assert main_reqs()[0].messages[0].content.endswith(DELEGATE_NUDGE)


def _first_main_prompt(cfg, tmp_path) -> str:
    ExploreMock.reset()
    ExploreMock.main = ["Final Answer: done"]
    asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    return main_reqs()[0].messages[0].content


def test_nudge_off_or_invisible_adds_nothing(tmp_path):
    base = _first_main_prompt(explore_config(), tmp_path)
    assert _first_main_prompt(explore_config({"nudge": False}), tmp_path) == base

    off = _first_main_prompt(explore_config(enabled=False), tmp_path)
    assert _first_main_prompt(explore_config({"nudge": True}, enabled=False), tmp_path) == off
    assert DELEGATE_NUDGE.strip() not in off

    cfg = dataclasses.replace(
        explore_config({"nudge": True}),
        tool_groups=ToolGroupSettings(disabled=("delegate",)),
    )
    assert DELEGATE_NUDGE.strip() not in _first_main_prompt(cfg, tmp_path)


def test_default_tool_list_excludes_delegate(tmp_path):
    for path in (ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml"):
        cfg = load_config(path)
        assert cfg.delegation.nudge is False
        names = Agent(cfg, tmp_path, ApprovalPolicy("auto")).registry_for().names()
        assert "delegate" not in names


def test_pinned_run_subagent_uses_pin(tmp_path):
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    go(apply_pin(explore_config(), "mock/strong"), tmp_path)
    pinned = [r for r in ExploreMock.calls if _task_of(r) == "qa"]
    assert pinned
    assert all(r.model == "mock/strong" for r in pinned)

    ExploreMock.reset()
    ExploreMock.subs = {"qa": ["Final Answer: A"]}
    ExploreMock.main = [explore("qa"), "Final Answer: done"]
    go(explore_config(), tmp_path)
    control = [r for r in ExploreMock.calls if _task_of(r) == "qa"]
    assert control
    assert all(r.model == "mock/cheap" for r in control)
