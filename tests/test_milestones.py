from __future__ import annotations

import asyncio
import json

import pytest

from cora.core import milestones
from cora.core.agent import Agent
from cora.core.budget import BudgetLimits, BudgetUsage
from cora.core.errors import ConfigError
from cora.core.milestones import (
    PROJECT_KEYS,
    RUN_ID_RE,
    CheckpointError,
    CheckpointStore,
    Milestone,
    PlanError,
    ProjectGovernor,
    ProjectPlan,
    ProjectRunner,
    load_plan,
    merge_policy,
    parse_plan,
    project_outcome,
)
from cora.core.observability import read_events
from cora.core.tools import ApprovalPolicy

GOOD = {"id": "a", "title": "A", "task": "do a"}


def plan_text(ms: list[dict], goal: str = "g") -> str:
    lines = [f"goal = {json.dumps(goal)}"]
    for m in ms:
        lines.append("[[milestones]]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in m.items()]
    return "\n".join(lines) + "\n"


PLAN2 = ProjectPlan("g", (Milestone("a", "A", "do a"), Milestone("b", "B", "do b")))


def build(mock_config, ws, plan):
    store = CheckpointStore(ws / ".cora" / "projects")
    cp = store.create(plan)
    gov = ProjectGovernor(BudgetLimits.from_agent(mock_config.agent))
    runner = ProjectRunner(
        cp,
        store,
        gov,
        lambda: Agent(mock_config, ws, ApprovalPolicy("auto"), governor=gov),
    )
    return store, cp, runner


def test_load_plan_valid(tmp_path):
    path = tmp_path / "plan.toml"
    path.write_text(
        plan_text(
            [
                {"id": "a", "title": "A", "task": "do a"},
                {"id": "b", "title": "B", "task": "do b", "check": "true"},
            ]
        ),
        encoding="utf-8",
    )
    assert load_plan(path) == ProjectPlan(
        "g", (Milestone("a", "A", "do a"), Milestone("b", "B", "do b", "true"))
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (None, "plan file not found"),
        ("goal = \n", "bad TOML"),
        ('goal = "g"\n', "no milestones"),
        ('goal = "g"\nmilestones = []\n', "no milestones"),
        ('goal = "g"\nmilestones = "x"\n', "array of tables"),
        (plan_text([GOOD, GOOD]), "duplicate id 'a'"),
        (plan_text([{"id": "a", "title": "A"}]), "'task' is missing or empty"),
        (plan_text([{**GOOD, "task": "  "}]), "'task' is missing or empty"),
        (plan_text([{**GOOD, "task": 3}]), "'task' must be a string"),
        (plan_text([{**GOOD, "id": 1}]), "'id' must be a non-empty string"),
        (plan_text([{**GOOD, "id": ""}]), "'id' must be a non-empty string"),
        (plan_text([{"id": "a", "task": "t"}]), "missing 'title'"),
        (
            'goal = 1\n[[milestones]]\nid = "a"\ntitle = "A"\ntask = "t"\n',
            "'goal' must be a string",
        ),
        (plan_text([{**GOOD, "check": 5}]), "'check' must be a non-empty string"),
        ("foo = 1\n" + plan_text([GOOD]), "unknown key 'foo'"),
        (plan_text([{**GOOD, "conditions": "x"}]), "'conditions' must be an array of tables"),
    ],
)
def test_load_plan_invalid(tmp_path, text, message):
    path = tmp_path / "plan.toml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(PlanError) as info:
        load_plan(path)
    assert message in str(info.value)
    assert isinstance(info.value, ConfigError)


def test_parse_plan_rejects_non_table():
    with pytest.raises(PlanError, match="must be a TOML table"):
        parse_plan([], "x")


def test_checkpoint_roundtrip(ws):
    store = CheckpointStore(ws / ".cora" / "projects")
    cp = store.create(PLAN2)
    assert store.path_for(cp.run_id).is_file()
    assert RUN_ID_RE.fullmatch(cp.run_id)
    assert store.load(cp.run_id).to_dict() == cp.to_dict()
    assert store.list_ids() == [cp.run_id]


def test_roundtrip_with_check_and_none(ws):
    store = CheckpointStore(ws / ".cora" / "projects")
    plan = ProjectPlan("g", (Milestone("a", "A", "do a", "true"), Milestone("b", "B", "do b")))
    cp = store.create(plan)
    assert store.load(cp.run_id).plan == plan


def test_atomic_replace_failure_keeps_previous(ws, monkeypatch):
    store = CheckpointStore(ws / ".cora" / "projects")
    cp = store.create(PLAN2)
    store.save(cp)
    cp.completed = ["a"]

    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(milestones.os, "replace", boom)
    with pytest.raises(OSError):
        store.save(cp)
    monkeypatch.undo()
    assert store.load(cp.run_id).completed == []
    assert not (store.dir_for(cp.run_id) / "checkpoint.json.tmp").exists()


def test_atomic_fsync_failure_keeps_previous(ws, monkeypatch):
    store = CheckpointStore(ws / ".cora" / "projects")
    cp = store.create(PLAN2)
    store.save(cp)
    cp.completed = ["a"]

    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(milestones.os, "fsync", boom)
    with pytest.raises(OSError):
        store.save(cp)
    monkeypatch.undo()
    assert store.load(cp.run_id).completed == []
    assert not (store.dir_for(cp.run_id) / "checkpoint.json.tmp").exists()


def test_load_errors(ws):
    store = CheckpointStore(ws / ".cora" / "projects")
    with pytest.raises(CheckpointError, match="project run not found"):
        store.load("20990101-000000-abcdef")
    cp = store.create(PLAN2)
    path = store.path_for(cp.run_id)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(CheckpointError, match="is unreadable"):
        store.load(cp.run_id)
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(CheckpointError, match="is unreadable"):
        store.load(cp.run_id)
    with pytest.raises(CheckpointError, match="invalid run id"):
        store.load("../x")


def test_project_governor_cumulative_tool_calls():
    gov = ProjectGovernor(BudgetLimits(tool_calls=3))
    gov.begin()
    gov.add_tool_calls(2)
    gov.commit()
    gov.begin(BudgetUsage())
    assert gov.usage().tool_calls == 2
    gov.add_tool_calls(1)
    assert gov.check_tool_call() == "tool_calls"


def test_project_governor_iterations_cost_wall():
    gov = ProjectGovernor(BudgetLimits(iterations=3))
    gov.begin()
    gov.add_iteration()
    gov.add_iteration()
    gov.commit()
    gov.begin()
    gov.add_iteration()
    assert gov.check_model_call() == "iterations"

    gov = ProjectGovernor(BudgetLimits(cost_usd=0.03))
    gov.begin()
    gov.add_cost(0.02)
    gov.commit()
    gov.begin()
    gov.add_cost(0.015)
    assert gov.check_model_call() == "cost"

    now = [0.0]
    gov = ProjectGovernor(BudgetLimits(wall_s=250), clock=lambda: now[0])
    gov.begin()
    now[0] = 200.0
    gov.commit()
    now[0] = 1000.0
    gov.begin()
    now[0] = 1040.0
    assert gov.check_model_call() is None
    now[0] = 1060.0
    assert gov.check_model_call() == "wall"


def test_project_governor_seed_and_warn_once():
    base = BudgetUsage(0.1, 4, 5.0, 3)
    gov = ProjectGovernor(BudgetLimits(tool_calls=10), base=base, clock=lambda: 0.0)
    gov.begin(BudgetUsage())
    assert gov.usage() == base
    gov.add_tool_calls(8)
    assert len(gov.drain_warnings()) == 1
    gov.commit()
    gov.begin(BudgetUsage())
    gov.add_tool_calls(1)
    assert gov.drain_warnings() == []


def test_runner_in_order(mock_config, ws, scripted):
    scripted.script[:] = ["Final Answer: A", "Final Answer: B"]
    store, cp, runner = build(mock_config, ws, PLAN2)
    assert asyncio.run(runner.execute()) == "final_answer"
    assert cp.completed == ["a", "b"]
    sid_a = cp.records["a"].session_id
    sid_b = cp.records["b"].session_id
    assert sid_a and sid_b and sid_a != sid_b
    assert store.load(cp.run_id).to_dict() == cp.to_dict()
    events = read_events(store.dir_for(cp.run_id) / "events.jsonl")
    assert sum(e["type"] == "milestone_start" for e in events) == 2
    assert sum(e["type"] == "checkpoint" for e in events) >= 3


def test_runner_skips_completed(mock_config, ws, scripted):
    scripted.script[:] = ["Final Answer: B"]
    store, cp, runner = build(mock_config, ws, PLAN2)
    cp.completed = ["a"]
    cp.records["a"].status = "completed"
    assert asyncio.run(runner.execute()) == "final_answer"
    assert len(scripted.calls) == 1
    first_user = next((m.content for m in scripted.calls[0].messages if m.role == "user"), "")
    assert "do b" in first_user


def test_runner_stop_requested_before_start(mock_config, ws, scripted):
    store, cp, runner = build(mock_config, ws, PLAN2)
    runner.request_stop()
    assert asyncio.run(runner.execute()) == "interrupted"
    assert cp.records["a"].status == "interrupted"
    assert len(scripted.calls) == 0


def test_project_outcome_keys(mock_config, ws):
    store, cp, runner = build(mock_config, ws, PLAN2)
    cp.records["a"].status = "running"
    doc = project_outcome(cp, None, stop_reason="interrupted", wall_s=1.0)
    assert set(doc) == set(PROJECT_KEYS)
    assert doc["milestones"][0]["status"] == "interrupted"


def test_merge_policy():
    assert merge_policy([None, None]) is None
    merged = merge_policy(
        [
            {"allow": 1, "deny": 2, "decisions": [{"x": 1}]},
            None,
            {"allow": 2, "deny": 1, "decisions": []},
        ]
    )
    assert merged["allow"] == 3
    assert merged["deny"] == 3
    assert merged["ask"] == 0
    assert merged["decisions"] == [{"x": 1}]
