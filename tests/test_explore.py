from __future__ import annotations

import asyncio
import time

import pytest

from conftest import act, native, tc
from cora.core.agent import Agent
from cora.core.delegation import EXPLORE_TOOLS, SUMMARY_TRUNCATED, explore_registry
from cora.core.errors import ConfigError, ProviderError
from cora.core.tools import ApprovalPolicy, ToolRegistry, default_tools
from cora.core.types import CompletionResponse
from explore_mock import ExploreMock, explore, explore_config, turn


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


def last_main():
    return main_reqs()[-1]


def go(cfg, tmp_path, policy=None):
    events: list[dict] = []
    agent = Agent(cfg, tmp_path, policy or ApprovalPolicy("auto"), on_event=events.append)
    r = asyncio.run(agent.run("main task"))
    return r, events


def test_mode_omitted_is_general(tmp_path):
    ExploreMock.subs = {"qg": ["Final Answer: G"]}
    ExploreMock.main = [act("delegate", {"task": "qg"}), "Final Answer: m"]
    r, _ = go(explore_config(), tmp_path)
    sub = sub_reqs()[0]
    assert "- edit_file:" in sub.messages[0].content
    assert "You are a sub-agent handling" in sub.messages[0].content
    assert r.session.delegations == 1
    assert r.session.explore_calls == 0

    ExploreMock.reset()
    ExploreMock.subs = {"qg": ["Final Answer: G"]}
    ExploreMock.main = [act("delegate", {"task": "qg", "mode": "fast"}), "Final Answer: m"]
    go(explore_config(), tmp_path)
    assert (
        "invalid arguments: 'mode' must be 'explore' or 'general'"
        in last_main().messages[-1].content
    )


@pytest.mark.slow
def test_explore_parallel_order_and_speed(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.delays = {"qa": 0.5, "qb": 0.3, "qc": 0.4}
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    start = time.monotonic()
    r, _ = go(explore_config(), tmp_path)
    elapsed = time.monotonic() - start
    assert r.answer == "done"
    assert elapsed < 0.95
    assert ExploreMock.peak == 3
    text = last_main().messages[-1].content
    i1 = text.index("Observation 1 (delegate): Sub-agent summary:\nA")
    i2 = text.index("Observation 2 (delegate): Sub-agent summary:\nB")
    i3 = text.index("Observation 3 (delegate): Sub-agent summary:\nC")
    assert i1 < i2 < i3


@pytest.mark.slow
def test_explore_concurrency_cap(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.delays = {"qa": 0.3, "qb": 0.3, "qc": 0.3}
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    start = time.monotonic()
    go(explore_config({"explore_concurrency": 2}), tmp_path)
    elapsed = time.monotonic() - start
    assert ExploreMock.peak == 2
    assert elapsed >= 0.5
    text = last_main().messages[-1].content
    i1 = text.index("Sub-agent summary:\nA")
    i2 = text.index("Sub-agent summary:\nB")
    i3 = text.index("Sub-agent summary:\nC")
    assert i1 < i2 < i3


@pytest.mark.slow
def test_explore_respects_max_parallel_tools(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.delays = {"qa": 0.1, "qb": 0.1, "qc": 0.1}
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    go(explore_config(agent={"max_parallel_tools": 1}), tmp_path)
    assert ExploreMock.peak == 1


@pytest.mark.slow
def test_parallel_explore_off_runs_serially(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.delays = {"qa": 0.1, "qb": 0.1, "qc": 0.1}
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    go(explore_config({"parallel_explore": False}), tmp_path)
    assert ExploreMock.peak == 1
    text = last_main().messages[-1].content
    i1 = text.index("Sub-agent summary:\nA")
    i2 = text.index("Sub-agent summary:\nB")
    i3 = text.index("Sub-agent summary:\nC")
    assert i1 < i2 < i3


@pytest.mark.slow
def test_general_is_barrier(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qg": ["Final Answer: G"],
        "qb": ["Final Answer: B"],
    }
    ExploreMock.delays = {"qa": 0.1, "qg": 0.1, "qb": 0.1}
    ExploreMock.main = [
        explore("qa") + "\n" + act("delegate", {"task": "qg"}) + "\n" + explore("qb"),
        "Final Answer: done",
    ]
    go(explore_config(), tmp_path)
    log = ExploreMock.log
    assert log.index(("start", "qg")) > log.index(("end", "qa"))
    assert log.index(("end", "qg")) < log.index(("start", "qb"))


def test_explore_is_read_only(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    ExploreMock.subs = {
        "qa": [
            act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
            act("run_shell", {"command": "echo hi > b.txt"}),
            explore("x"),
            "Final Answer: s",
        ]
    }
    ExploreMock.main = [explore("qa"), "Final Answer: m"]
    go(explore_config(), tmp_path)
    subs = sub_reqs()
    assert "unknown tool 'edit_file'" in subs[1].messages[-1].content
    assert "unknown tool 'run_shell'" in subs[2].messages[-1].content
    assert "unknown tool 'delegate'" in subs[3].messages[-1].content
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert not (tmp_path / "b.txt").exists()
    assert "- read_file:" in subs[0].messages[0].content
    assert "- edit_file:" not in subs[0].messages[0].content
    assert explore_registry(ToolRegistry(default_tools())).names() == list(EXPLORE_TOOLS)


@pytest.mark.parametrize("case", ["error", "timeout"])
@pytest.mark.slow
def test_explore_failure_isolated(tmp_path, case):
    ExploreMock.subs = {"qa": ["Final Answer: A"], "qc": ["Final Answer: C"]}
    if case == "error":
        ExploreMock.subs["qb"] = [ProviderError("boom")]
        expected = "delegation failed (error: ProviderError: boom)"
    else:
        ExploreMock.subs["qb"] = ["Final Answer: B"]
        ExploreMock.delays = {"qb": 2.0}
        expected = "delegation failed (timeout)"
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    start = time.monotonic()
    r, _ = go(explore_config({"timeout_s": 0.3}), tmp_path)
    elapsed = time.monotonic() - start
    text = last_main().messages[-1].content
    assert "Sub-agent summary:\nA" in text
    assert "Sub-agent summary:\nC" in text
    assert expected in text.split("Observation 3")[0]
    assert r.answer == "done"
    assert r.session.delegation_stats["ok"] == 2
    assert r.session.delegation_stats["failed"] == 1
    if case == "timeout":
        assert elapsed < 1.5


def test_failed_sibling_waiting_still_runs(tmp_path):
    ExploreMock.subs = {
        "qa": [ProviderError("boom")],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    go(explore_config({"explore_concurrency": 1}), tmp_path)
    text = last_main().messages[-1].content
    assert "Sub-agent summary:\nB" in text
    assert "Sub-agent summary:\nC" in text


def test_failure_disables_later_turns_only(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": [ProviderError("boom")],
        "qc": ["Final Answer: C"],
        "qd": ["Final Answer: D"],
    }
    ExploreMock.main = [turn("qa", "qb", "qc"), explore("qd"), "Final Answer: done"]
    go(explore_config(), tmp_path)
    assert (
        "delegation is unavailable for the rest of this request"
        in last_main().messages[-1].content
    )
    assert not any(_task_of(q) == "qd" for q in ExploreMock.calls)


def test_explore_caps_refuse_without_running(tmp_path):
    ExploreMock.subs = {
        "qa": ["Final Answer: A"],
        "qb": ["Final Answer: B"],
        "qc": ["Final Answer: C"],
    }
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    r, _ = go(explore_config({"explore_max_calls": 2}), tmp_path)
    text = last_main().messages[-1].content
    assert "explore limit reached (2 per session)" in text
    assert "do the subtask yourself" in text
    assert not any(_task_of(q) == "qc" for q in ExploreMock.calls)
    assert r.session.delegation_stats["refused"] == 1

    ExploreMock.reset()
    ExploreMock.subs = {"qa": ["Final Answer: A"], "qb": ["Final Answer: B"]}
    ExploreMock.main = [explore("qa"), explore("qb"), "Final Answer: done"]
    go(explore_config({"max_total_tokens": 1}), tmp_path)
    assert "delegation budget reached" in last_main().messages[-1].content
    assert not any(_task_of(q) == "qb" for q in ExploreMock.calls)

    ExploreMock.reset()
    ExploreMock.subs = {"qa": ["Final Answer: A"], "qb": ["Final Answer: B"]}
    ExploreMock.main = [explore("qa"), explore("qb"), "Final Answer: done"]
    go(explore_config({"max_total_cost_usd": 1e-9}), tmp_path)
    assert "delegation budget reached" in last_main().messages[-1].content
    assert not any(_task_of(q) == "qb" for q in ExploreMock.calls)


def test_plan_mode_general_denied_explore_runs(tmp_path):
    ExploreMock.subs = {"qg": ["Final Answer: G"], "qa": ["Final Answer: A"]}
    ExploreMock.main = [act("delegate", {"task": "qg"}), explore("qa"), "Final Answer: m"]
    agent = Agent(explore_config(), tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    asyncio.run(agent.run("main task"))
    assert not any(_task_of(q) == "qg" for q in ExploreMock.calls)
    assert "Sub-agent summary:\nA" in last_main().messages[-1].content

    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    ExploreMock.reset()
    ExploreMock.subs = {
        "qa": [act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}), "Final Answer: s"]
    }
    ExploreMock.main = [explore("qa"), "Final Answer: m"]
    asked: list[str] = []
    policy = ApprovalPolicy("ask", review=lambda req: (asked.append(req.tool), "no")[1])
    agent = Agent(explore_config(), tmp_path, policy)
    agent.ctx.plan_mode = True
    asyncio.run(agent.run("main task"))
    assert asked == []
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_explore_native_and_react_same_format(tmp_path, protocol):
    ExploreMock.subs = {"qa": ["Final Answer: A"], "qb": ["Final Answer: B"]}
    if protocol == "react":
        cfg = explore_config()
        ExploreMock.main = [turn("qa", "qb"), "Final Answer: done"]
    else:
        cfg = explore_config(agent={"tool_protocol": "native"})
        ExploreMock.main = [
            native(
                tc("delegate", {"task": "qa", "mode": "explore"}, id="c1"),
                tc("delegate", {"task": "qb", "mode": "explore"}, id="c2"),
            ),
            CompletionResponse("done", 10, 5, "mock/cheap"),
        ]
    events: list[dict] = []
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"), on_event=events.append)
    asyncio.run(agent.run("main task"))
    heads = [
        e["output_head"]
        for e in events
        if e["type"] == "tool_call" and e["tool"] == "delegate" and not e.get("sub")
    ]
    assert heads == ["Sub-agent summary:\nA", "Sub-agent summary:\nB"]
    if protocol == "native":
        schema = next(
            t for t in ExploreMock.calls[0].tools if t["function"]["name"] == "delegate"
        )
        assert schema["function"]["parameters"]["properties"]["mode"]["enum"] == [
            "explore",
            "general",
        ]
        tool_msgs = [m.content for m in last_main().messages if m.role == "tool"]
        assert tool_msgs == ["Sub-agent summary:\nA", "Sub-agent summary:\nB"]


@pytest.mark.parametrize("mode", ["explore", "general"])
def test_summary_cap_and_no_transcript(tmp_path, mode):
    (tmp_path / "big.txt").write_text("SECRET_MARKER " + "x" * 3000, encoding="utf-8")
    big_answer = "Final Answer: " + "y" * 1000
    ExploreMock.subs = {"qa": [act("read_file", {"path": "big.txt"}), big_answer]}
    ExploreMock.main = [act("delegate", {"task": "qa", "mode": mode}), "Final Answer: done"]
    go(explore_config({"summary_max_chars": 200}), tmp_path)
    obs = last_main().messages[-1].content
    prefix = "Observation: Sub-agent summary:\n"
    assert obs.startswith(prefix)
    body = obs[len(prefix) :]
    assert len(body) <= 200
    assert body.endswith(SUMMARY_TRUNCATED)
    assert not any("SECRET_MARKER" in m.content for q in main_reqs() for m in q.messages)


def test_delegation_config_validation():
    for bad in ({"explore_concurrency": 0}, {"summary_max_chars": 50}, {"parallel_explore": "yes"}):
        with pytest.raises(ConfigError):
            explore_config(bad)
