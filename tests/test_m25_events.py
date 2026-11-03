from __future__ import annotations

import asyncio
import json

from cora.core.config import load_config
from cora.core.milestones import load_plan
from cora.core.observability import read_events
from cora.core.planner import PLAN_DOC_KEYS, plan_project
from cora.core.policy import planning_policy
from m20_trial import ROOT
from test_m25_planner import PJ
from test_project_cli import base, pdoc, run_cli
from test_project_plan_cli import VALID, plandoc

SECRET = "sk-or-v1-m25testsecret0000"
ERR = (
    "planner reply invalid after one repair attempt: "
    "model reply is not valid JSON: Expecting value (line 1, column 1)"
)
TWO_PLAIN = {
    "goal": "g",
    "milestones": [
        {"id": "m1", "title": "one", "task": "alpha-task"},
        {"id": "m2", "title": "two", "task": "beta-task"},
    ],
}
ENVELOPE = {"ts", "type"}
REJECT_KEYS = {
    "stage", "call", "error", "cause", "finish_reason", "tokens_out",
    "reply_chars", "reply", "reply_cut",
}


def _rejected(ws):
    path = ws / ".cora" / "planner" / "events.jsonl"
    return [e for e in read_events(path) if e["type"] == "plan_reply_rejected"]


def test_rejected_reply_saved_and_scrubbed(scripted, ws, cfg_file, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    scripted.script.extend([f"oops {SECRET}", "still not json"])
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "p.toml"), "--json", *base(ws, cfg_file),
    ])
    d = plandoc(result)
    assert result.exit_code == 2
    assert d["errors"] == [ERR]
    events = _rejected(ws)
    assert [(e["stage"], e["cause"]) for e in events] == [
        ("schema", "no_object"),
        ("schema_repair", "no_object"),
    ]
    assert "<redacted>" in events[0]["reply"]
    assert SECRET not in events[0]["reply"]
    assert SECRET not in (ws / ".cora" / "planner" / "events.jsonl").read_text(encoding="utf-8")


def test_no_planner_log_on_success(scripted, ws, cfg_file):
    scripted.script.append(json.dumps(VALID))
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "p.toml"), "--json", *base(ws, cfg_file),
    ])
    assert result.exit_code == 0
    assert not (ws / ".cora" / "planner").exists()


def test_run_goal_events_copied(scripted, ws, cfg_file):
    scripted.script.extend(["bad", json.dumps(TWO_PLAIN), "Final Answer: A", "Final Answer: B"])
    result = run_cli([
        "project", "run", "--goal", "g", "--headless", "--json", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    events = read_events(ws / ".cora" / "projects" / d["run_id"] / "events.jsonl")
    types = [e["type"] for e in events]
    rejected = [i for i, t in enumerate(types) if t == "plan_reply_rejected"]
    assert len(rejected) == 1
    later = [types.index(t) for t in ("plan_policy", "milestone_start") if t in types]
    assert rejected[0] < min(later)


def test_policy_repair_unparsable_reported(ws):
    policy = planning_policy(load_config(ROOT / "cora.toml").policy, ws, "policy")
    bad = json.dumps({
        "goal": "g",
        "milestones": [{"id": "m1", "title": "t", "task": "x", "check": "cd x && ls"}],
    })
    replies = iter([bad, "x"])
    rejects: list[dict] = []

    async def call(msgs):
        return next(replies)

    plan = asyncio.run(plan_project(
        "g", call, policy=policy, on_reject=rejects.append,
    ))
    assert [r["stage"] for r in rejects] == ["policy_repair"]
    assert plan.milestones[0].check is None


def test_first_rejected_then_repaired_cli(scripted, ws, cfg_file):
    scripted.script.extend(["bad", PJ])
    out = ws / "p.toml"
    result = run_cli([
        "project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file),
    ])
    plandoc(result)
    assert result.exit_code == 0
    events = _rejected(ws)
    assert len(events) == 1
    event = events[0]
    assert event["stage"] == "schema"
    assert event["call"] == 1
    assert set(event) - ENVELOPE == REJECT_KEYS


def test_reply_capped(scripted, ws, cfg_file):
    scripted.script.extend(["x" * 25000, PJ])
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "p.toml"), "--json", *base(ws, cfg_file),
    ])
    assert result.exit_code == 0
    events = _rejected(ws)
    assert len(events) == 1
    assert events[0]["reply_chars"] == 25000
    assert len(events[0]["reply"]) == 20000
    assert events[0]["reply_cut"] is True


def test_cli_prose_wrapped_plan_ok(scripted, ws, cfg_file):
    scripted.script.append("Plan for {the goal} below.\n" + PJ + "\nDone {ok}.")
    out = ws / "p.toml"
    result = run_cli([
        "project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file),
    ])
    d = plandoc(result)
    assert result.exit_code == 0
    assert len(scripted.calls) == 1
    expected = json.loads(PJ)["milestones"]
    loaded = load_plan(out)
    assert [m.id for m in loaded.milestones] == [m["id"] for m in expected]
    assert not (ws / ".cora" / "planner").exists()
    assert set(d) == set(PLAN_DOC_KEYS)
