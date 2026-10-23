from __future__ import annotations

import asyncio
import json
import sys
import time

import pytest

from cora.core.agent import Agent
from cora.core.budget import BudgetLimits
from cora.core.milestones import (
    CheckpointStore,
    Condition,
    Milestone,
    MilestoneRecord,
    ProjectGovernor,
    ProjectPlan,
    ProjectRunner,
    load_plan,
    milestone_list,
    project_outcome,
    run_condition,
)
from cora.core.tools import ApprovalPolicy
from cora.core.tools.builtin import RunShellTool

PY = sys.executable
COND = f"{PY} -c \"import os,sys; sys.exit(0 if os.path.exists('done.txt') else 1)\""


def P(*ms: Milestone) -> ProjectPlan:
    return ProjectPlan("g", ms)


M0 = Milestone("z", "Z", "zeta-task")
M1 = Milestone("a", "A", "alpha-task", None, (Condition("command", cmd=COND),))
M2 = Milestone("b", "B", "beta-task")


def gated(mock_config, ws, plan, limits=None, **kw):
    store = CheckpointStore(ws / ".cora" / "projects")
    cp = store.create(plan)
    gov = ProjectGovernor(limits or BudgetLimits.from_agent(mock_config.agent))
    runner = ProjectRunner(
        cp,
        store,
        gov,
        lambda: Agent(mock_config, ws, ApprovalPolicy("auto"), governor=gov),
        **kw,
    )
    return store, cp, runner, gov


def resume(mock_config, ws, store, run_id, **kw):
    cp = store.load(run_id)
    gov = ProjectGovernor(BudgetLimits.from_agent(mock_config.agent))
    runner = ProjectRunner(
        cp,
        store,
        gov,
        lambda: Agent(mock_config, ws, ApprovalPolicy("auto"), governor=gov),
        **kw,
    )
    return cp, runner, gov


def first_user(req) -> str:
    return next(m.content for m in req.messages if m.role == "user")


def test_load_plan_with_conditions(tmp_path):
    path = tmp_path / "plan.toml"
    path.write_text(
        'goal = "g"\n[[milestones]]\nid = "a"\ntitle = "A"\ntask = "t"\n'
        'conditions = [{ kind = "command", cmd = "true" }, '
        '{ kind = "file_exists", path = "x.txt" }]\n',
        encoding="utf-8",
    )
    plan = load_plan(path)
    assert plan.milestones[0].conditions == (
        Condition("command", cmd="true"),
        Condition("file_exists", path="x.txt"),
    )
    assert plan.to_dict()["milestones"][0]["conditions"] == [
        {"kind": "command", "cmd": "true"},
        {"kind": "file_exists", "path": "x.txt"},
    ]


def test_load_plan_with_conditions_table_array(tmp_path):
    path = tmp_path / "plan.toml"
    path.write_text(
        'goal = "g"\n[[milestones]]\nid = "a"\ntitle = "A"\ntask = "t"\n'
        '[[milestones.conditions]]\nkind = "command"\ncmd = "true"\n',
        encoding="utf-8",
    )
    plan = load_plan(path)
    assert plan.milestones[0].conditions == (Condition("command", cmd="true"),)


def test_condition_retry_then_pass(mock_config, ws, scripted):
    store, cp, runner, gov = gated(mock_config, ws, P(M1, M2))

    def make_done(req):
        (ws / "done.txt").write_text("ok")
        return "Final Answer: a2"

    scripted.script = ["Final Answer: a1", make_done, "Final Answer: b"]
    assert asyncio.run(runner.execute()) == "final_answer"
    assert cp.completed == ["a", "b"]
    assert cp.records["a"].gate["attempts"] == 2
    assert cp.records["a"].gate["passed"] is True
    text = first_user(scripted.calls[1])
    assert "alpha-task" in text
    assert "done.txt" in text
    assert "[completion check failed]" in text
    assert len(scripted.calls) == 3


def test_condition_fails_twice_gate_failed(mock_config, ws, scripted):
    store, cp, runner, gov = gated(mock_config, ws, P(M0, M1, M2))
    scripted.script = ["Final Answer: a1", "Final Answer: a2", "Final Answer: never"]
    assert asyncio.run(runner.execute()) == "gate_failed"
    assert cp.records["z"].status == "completed"
    assert cp.records["a"].status == "failed"
    assert cp.records["a"].stop_reason == "gate_failed"
    assert cp.records["b"].status == "pending"
    gate = cp.records["a"].gate
    assert gate["attempts"] == 2
    assert gate["failed_condition"] == f"command `{COND}`"
    assert not any("beta-task" in first_user(r) for r in scripted.calls)
    out = project_outcome(cp, gov, stop_reason="gate_failed", wall_s=0)
    assert out["exit_code"] == 1
    assert out["ok"] is False
    assert out["milestones"][1]["gate"]["attempts"] == 2
    assert "gate" not in out["milestones"][0]
    assert "gate" not in out["milestones"][2]


def test_gate_retries_zero(mock_config, ws, scripted):
    store, cp, runner, gov = gated(mock_config, ws, P(M1, M2), gate_retries=0)
    scripted.script = ["Final Answer: a1", "Final Answer: never"]
    assert asyncio.run(runner.execute()) == "gate_failed"
    assert cp.records["a"].gate["attempts"] == 1
    assert len(scripted.calls) == 1


def test_resume_after_gate_failed_fresh_allowance(mock_config, ws, scripted):
    store, cp, runner, gov = gated(mock_config, ws, P(M0, M1, M2))
    scripted.script = ["Final Answer: a1", "Final Answer: a2"]
    assert asyncio.run(runner.execute()) == "gate_failed"
    (ws / "done.txt").write_text("ok")
    scripted.script = ["Final Answer: a3", "Final Answer: b"]
    scripted.calls.clear()
    cp2, runner2, gov2 = resume(mock_config, ws, store, cp.run_id)
    assert asyncio.run(runner2.execute()) == "final_answer"
    assert cp2.records["a"].gate["attempts"] == 1
    assert cp2.records["a"].gate["passed"] is True
    assert len(scripted.calls) == 2


def test_kill_during_retry_resume(mock_config, ws, scripted):
    store, cp, _, _ = gated(mock_config, ws, P(M0, M1, M2))
    cp.completed = ["z"]
    cp.records["z"] = MilestoneRecord(status="completed")
    cp.records["a"] = MilestoneRecord(
        status="running",
        gate={
            "attempts": 1,
            "passed": False,
            "failed_condition": f"command `{COND}`",
            "feedback": "FEEDBACK-MARK",
        },
    )
    cp.current = "a"
    store.save(cp)
    cp2, runner2, gov2 = resume(mock_config, ws, store, cp.run_id)
    scripted.script = ["Final Answer: a2", "Final Answer: never"]
    assert asyncio.run(runner2.execute()) == "gate_failed"
    assert cp2.records["a"].gate["attempts"] == 2
    assert len(scripted.calls) == 1
    assert "FEEDBACK-MARK" in first_user(scripted.calls[0])
    assert cp2.records["z"].status == "completed"


def test_kill_during_retry_resume_passes(mock_config, ws, scripted):
    store, cp, _, _ = gated(mock_config, ws, P(M0, M1, M2))
    cp.completed = ["z"]
    cp.records["z"] = MilestoneRecord(status="completed")
    cp.records["a"] = MilestoneRecord(
        status="running",
        gate={
            "attempts": 1,
            "passed": False,
            "failed_condition": f"command `{COND}`",
            "feedback": "FEEDBACK-MARK",
        },
    )
    cp.current = "a"
    store.save(cp)
    (ws / "done.txt").write_text("ok")
    cp2, runner2, gov2 = resume(mock_config, ws, store, cp.run_id)
    scripted.script = ["Final Answer: a2", "Final Answer: b"]
    assert asyncio.run(runner2.execute()) == "final_answer"
    assert cp2.records["a"].gate["attempts"] == 2
    assert cp2.records["a"].gate["passed"] is True
    assert cp2.completed == ["z", "a", "b"]


def test_passing_conditions_write_checkpoint(mock_config, ws, scripted):
    (ws / "f.txt").write_text("x")
    m = Milestone(
        "a",
        "A",
        "alpha-task",
        None,
        (
            Condition("command", cmd=f'{PY} -c "pass"'),
            Condition("file_exists", path="f.txt"),
        ),
    )
    store, cp, runner, gov = gated(mock_config, ws, P(m))
    scripted.script = ["Final Answer: a"]
    assert asyncio.run(runner.execute()) == "final_answer"
    data = json.loads(store.path_for(cp.run_id).read_text(encoding="utf-8"))
    assert data["completed"] == ["a"]
    assert data["milestones"]["a"]["gate"]["attempts"] == 1


def test_conditions_count_tool_calls_and_trip(mock_config, ws, scripted):
    limits = BudgetLimits(cost_usd=1.0, iterations=30, wall_s=None, tool_calls=1)
    m = Milestone(
        "a", "A", "alpha-task", None, (Condition("file_exists", path="missing.txt"),)
    )
    store, cp, runner, gov = gated(mock_config, ws, P(m), limits=limits)
    scripted.script = ["Final Answer: a1", "Final Answer: a2"]
    assert asyncio.run(runner.execute()) == "budget_exceeded"
    assert gov.tripped == "tool_calls"
    assert cp.records["a"].status == "failed"
    assert cp.records["a"].gate["attempts"] == 1
    assert project_outcome(cp, gov, stop_reason="budget_exceeded", wall_s=0)["exit_code"] == 4


def test_no_conditions_unchanged(mock_config, ws, scripted):
    m3 = Milestone("c", "C", "gamma-task")
    store, cp, runner, gov = gated(mock_config, ws, P(M2, m3))
    scripted.script = ["Final Answer: b", "Final Answer: c"]
    assert asyncio.run(runner.execute()) == "final_answer"
    data = json.loads(store.path_for(cp.run_id).read_text(encoding="utf-8"))
    assert "planning" not in data
    for rec in data["milestones"].values():
        assert "gate" not in rec
    for item in milestone_list(cp):
        assert set(item) == {"id", "status", "session_id", "cost_usd"}


def ctx_for(mock_config, ws, approval):
    return Agent(mock_config, ws, ApprovalPolicy(approval)).ctx


def test_condition_policy_denied(mock_config, ws, monkeypatch):
    secret = ws.parent / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    ctx = ctx_for(mock_config, ws, "policy")

    async def boom(*args, **kwargs):
        raise AssertionError("must not run")

    monkeypatch.setattr(RunShellTool, "run", boom)
    ok, out = asyncio.run(
        asyncio.wait_for(
            run_condition(
                Condition("command", cmd="cat ../secret.txt"),
                ctx,
                timeout_s=30,
                max_chars=2000,
            ),
            30,
        )
    )
    assert ok is False
    assert "TOPSECRET" not in out


def test_condition_preflight_denied_in_auto(mock_config, ws):
    secret = ws.parent / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    ctx = ctx_for(mock_config, ws, "auto")
    ok, out = asyncio.run(
        asyncio.wait_for(
            run_condition(
                Condition("command", cmd="cat ../secret.txt"),
                ctx,
                timeout_s=30,
                max_chars=2000,
            ),
            30,
        )
    )
    assert ok is False
    assert out.startswith("denied:")
    assert "TOPSECRET" not in out


def test_condition_file_exists_escape(mock_config, ws):
    secret = ws.parent / "secret"
    secret.write_text("TOPSECRET", encoding="utf-8")
    (ws / "link").symlink_to(secret)
    ctx = ctx_for(mock_config, ws, "auto")
    ok, out = asyncio.run(
        run_condition(Condition("file_exists", path="link"), ctx, timeout_s=30, max_chars=2000)
    )
    assert ok is False
    assert "denied" in out


def test_condition_output_tail(mock_config, ws):
    ctx = ctx_for(mock_config, ws, "auto")
    cmd = f"{PY} -c \"print('x'*20000 + 'END'); raise SystemExit(1)\""
    ok, out = asyncio.run(
        run_condition(Condition("command", cmd=cmd), ctx, timeout_s=30, max_chars=100)
    )
    assert ok is False
    assert len(out) <= 100
    assert "END" in out


@pytest.mark.slow
def test_condition_timeout(mock_config, ws):
    ctx = ctx_for(mock_config, ws, "auto")
    cmd = f'{PY} -c "import time; time.sleep(30)"'
    started = time.monotonic()
    ok, out = asyncio.run(
        run_condition(Condition("command", cmd=cmd), ctx, timeout_s=1, max_chars=2000)
    )
    assert ok is False
    assert "timeout after 1s" in out
    assert time.monotonic() - started < 15
