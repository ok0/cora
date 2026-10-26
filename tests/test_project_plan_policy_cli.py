from __future__ import annotations

import json

from conftest import CFG_TOML
from cora.core.observability import read_events
from cora.core.planner import UNGATED_WARNING
from test_project_cli import base, pdoc, run_cli, write_cfg
from test_project_plan_cli import VALID, plandoc

DENIED = {
    "goal": "g",
    "milestones": [
        {
            "id": "m1",
            "title": "one",
            "task": "alpha-task",
            "conditions": [{"kind": "command", "cmd": "cd x && ls"}],
        },
    ],
}


def test_plan_cli_policy_doc(scripted, ws, cfg_file):
    scripted.script.extend([json.dumps(DENIED)] * 2)
    out = ws / "plan.toml"
    result = run_cli([
        "project", "plan", "g", "-o", str(out), "--json", "--approval", "policy",
        *base(ws, cfg_file),
    ])
    d = plandoc(result)
    assert result.exit_code == 0
    assert d["plan_policy"]["ungated"] == ["m1"]
    warning = UNGATED_WARNING.format(id="m1")
    assert warning in result.stderr
    assert warning in d["warnings"]
    text = out.read_text(encoding="utf-8")
    assert "ungated = true" in text
    assert "check" not in text


def test_plan_cli_no_policy_in_ask_mode(scripted, ws, cfg_file):
    scripted.script.append(json.dumps(VALID))
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    d = plandoc(result)
    assert result.exit_code == 0
    assert len(scripted.calls) == 1
    assert d["plan_policy"] is None
    assert "Shell policy" not in scripted.calls[0].messages[0].content


def test_run_goal_ungated_report(scripted, ws, cfg_file):
    scripted.script.extend([json.dumps(DENIED), json.dumps(DENIED), "Final Answer: A"])
    result = run_cli(["project", "run", "--goal", "g", "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 0
    assert d["exit_code"] == 0
    events = read_events(ws / ".cora" / "projects" / d["run_id"] / "events.jsonl")
    policy_events = [e for e in events if e["type"] == "plan_policy"]
    assert len(policy_events) == 1
    assert policy_events[0]["ungated"] == ["m1"]
    assert d["ungated_milestones"] == ["m1"]
    assert UNGATED_WARNING.format(id="m1") in result.stderr


def test_policy_repairs_invalid_exit_2(scripted, ws, cfg_file, tmp_path):
    bad = write_cfg(
        tmp_path, CFG_TOML + "\n[project]\npolicy_repairs = 9\n", name="bad_repairs.toml",
    )
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "plan.toml"), "--json", *base(ws, bad),
    ])
    plandoc(result)
    assert result.exit_code == 2

    unknown = write_cfg(tmp_path, CFG_TOML + "\n[project]\nbogus = 1\n", name="bad_key.toml")
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "plan.toml"), "--json", *base(ws, unknown),
    ])
    plandoc(result)
    assert result.exit_code == 2


def test_plan_cli_invalid_approval_exit_2(scripted, ws, cfg_file):
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "plan.toml"), "--json", "--approval", "bogus",
        *base(ws, cfg_file),
    ])
    assert result.exit_code == 2
