from __future__ import annotations

import asyncio
import dataclasses

from conftest import act, native, run_repl, tc, with_agent
from cora.core.agent import Agent
from cora.core.config import DelegationSettings
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, Workspace, default_tools
from cora.core.types import CompletionResponse

EDIT = {"path": "a.txt", "old": "hello", "new": "bye"}


def _plan_ctx(root):
    return ToolContext(Workspace(root), ApprovalPolicy("auto"), plan_mode=True)


def test_registry_denies_writes_in_auto(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    reg = ToolRegistry(default_tools())
    ctx = _plan_ctx(tmp_path)
    res = asyncio.run(reg.execute("edit_file", EDIT, ctx))
    assert res.ok is False
    assert "plan mode is on" in res.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    res = asyncio.run(reg.execute("run_shell", {"command": "touch x"}, ctx))
    assert res.ok is False
    assert "plan mode is on" in res.output
    assert not (tmp_path / "x").exists()
    assert asyncio.run(reg.execute("read_file", {"path": "a.txt"}, ctx)).ok
    assert asyncio.run(reg.execute("list_files", {}, ctx)).ok
    assert asyncio.run(reg.execute("todo_write", {"todos": []}, ctx)).ok


def test_react_plan_mode(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    scripted.script[:] = [
        act("edit_file", EDIT),
        act("read_file", {"path": "a.txt"}),
        act("submit_plan", {"plan": "1. change a"}),
        "Final Answer: planned",
    ]
    asyncio.run(agent.run("make a plan"))
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert "plan mode is on" in scripted.calls[1].messages[-1].content
    assert "hello" in scripted.calls[2].messages[-1].content
    assert agent.ctx.submitted_plan == "1. change a"
    assert "- submit_plan:" in scripted.calls[0].messages[0].content
    assert "PLAN MODE" in scripted.calls[0].messages[0].content


def test_native_plan_mode(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    scripted.script[:] = [
        native(tc("edit_file", EDIT)),
        native(tc("submit_plan", {"plan": "p"}, id="c2")),
        CompletionResponse("done", 10, 5, "mock/cheap"),
    ]
    asyncio.run(agent.run("make a plan"))
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert any(
        m.role == "tool" and "plan mode is on" in m.content for m in scripted.calls[1].messages
    )
    assert "submit_plan" in {t["function"]["name"] for t in scripted.calls[0].tools}
    assert agent.ctx.submitted_plan == "p"


def test_submit_plan_absent_outside_plan_mode(mock_config, scripted, tmp_path):
    scripted.script[:] = [act("submit_plan", {"plan": "x"}), "Final Answer: ok"]
    asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("task"))
    assert "unknown tool" in scripted.calls[1].messages[-1].content
    assert "- submit_plan:" not in scripted.calls[0].messages[0].content


def test_delegated_subagent_plan_mode(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    cfg = dataclasses.replace(mock_config, delegation=DelegationSettings(enabled=True))
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    scripted.script[:] = [act("delegate", {"task": "edit a"}), "Final Answer: main done"]
    r = asyncio.run(agent.run("main task"))
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert (
        "denied: plan mode is on, so 'delegate' was not run"
        in scripted.calls[1].messages[-1].content
    )
    assert len(scripted.calls) == 2
    assert r.answer == "main done"


def test_repl_plan_approve_then_diff_review(scripted, ws, cfg_file):
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    scripted.script[:] = [
        act("edit_file", EDIT),
        act("submit_plan", {"plan": "1. replace hello with bye"}),
        "Final Answer: planned",
        act("edit_file", EDIT),
        "Final Answer: done",
    ]
    out = run_repl(
        ws,
        cfg_file,
        ["/plan", "make a plan", "a", "y", "/status", "/exit"],
        approval="ask",
    )
    assert "[plan] > " in out
    assert "plan mode is on" in scripted.calls[1].messages[-1].content
    assert "1. replace hello with bye" in out
    assert "Plan: [a]pprove" in out
    assert "-hello" in out
    assert "+bye" in out
    assert out.count("Allow?") == 1
    assert (ws / "a.txt").read_text(encoding="utf-8") == "bye\n"
    assert "plan mode: off" in out
    assert any("Approved plan" in m.content for m in scripted.calls[3].messages)


def test_repl_plan_reject_keeps_mode(scripted, ws, cfg_file):
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    scripted.script[:] = [
        act("submit_plan", {"plan": "p1"}),
        "Final Answer: x",
        act("edit_file", EDIT),
        "Final Answer: z",
    ]
    out = run_repl(
        ws,
        cfg_file,
        ["/plan", "plan it", "r", "", "edit now", "/status", "/exit"],
        approval="auto",
    )
    assert (ws / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert "Plan rejected" in out
    assert "plan mode: on" in out
    assert "plan mode is on" in scripted.calls[3].messages[-1].content


def test_repl_plan_cancel_and_off(scripted, ws, cfg_file):
    scripted.script[:] = [act("submit_plan", {"plan": "p"}), "Final Answer: x"]
    out = run_repl(ws, cfg_file, ["/plan", "plan it", "c", "/status", "/exit"])
    assert "Plan cancelled" in out
    assert "plan mode: off" in out
    out = run_repl(ws, cfg_file, ["/plan", "/plan off", "/plan bogus", "/exit"])
    assert "plan mode: off" in out
    assert "usage: /plan [off]" in out
