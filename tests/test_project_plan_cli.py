from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import CFG_TOML, PY, act
from cora.core import planner as planner_mod
from cora.core.errors import ProviderAccountError
from cora.core.milestones import load_plan
from cora.core.planner import PLAN_DOC_KEYS, plan_from_text
from cora.core.types import CompletionResponse
from test_project_cli import base, cp_json, pdoc, run_cli, statuses, task_calls, write_cfg

COND_PASS = f"{PY} -c \"pass\""
COND = f"{PY} -c \"import os,sys; sys.exit(0 if os.path.exists('done.txt') else 1)\""

VALID = {
    "goal": "g",
    "milestones": [
        {
            "id": "m1",
            "title": "one",
            "task": "alpha-task",
            "conditions": [
                {"kind": "command", "cmd": COND_PASS},
                {"kind": "file_exists", "path": "a.txt"},
            ],
        },
        {"id": "m2", "title": "two", "task": "beta-task"},
    ],
}

TWO_PLAIN = {
    "goal": "g",
    "milestones": [
        {"id": "m1", "title": "one", "task": "alpha-task"},
        {"id": "m2", "title": "two", "task": "beta-task"},
    ],
}

GATE_PLAN = (
    'goal = "ship"\n'
    '[[milestones]]\nid = "m1"\ntitle = "one"\ntask = "alpha-task"\n'
    '[[milestones]]\nid = "m2"\ntitle = "two"\ntask = "beta-task"\n'
    "conditions = [ { kind = \"command\", cmd = " + json.dumps(COND) + " } ]\n"
    '[[milestones]]\nid = "m3"\ntitle = "three"\ntask = "gamma-task"\n'
)


def plandoc(result) -> dict:
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    d = json.loads(result.stdout)
    assert set(d) == set(PLAN_DOC_KEYS)
    assert d["exit_code"] == result.exit_code
    return d


def R(text: str, cost: float) -> CompletionResponse:
    return CompletionResponse(text, 100, 50, "mock/cheap", cost_usd=cost)


def write_gate_plan(tmp_path: Path) -> Path:
    path = tmp_path / "gate.toml"
    path.write_text(GATE_PLAN, encoding="utf-8")
    return path


def test_plan_writes_file_one_call(scripted, ws, cfg_file):
    scripted.script.append(json.dumps(VALID))
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    assert result.exit_code == 0
    assert len(scripted.calls) == 1
    loaded = load_plan(out)
    expected = plan_from_text(json.dumps(VALID), max_milestones=8)
    assert [m.id for m in loaded.milestones] == [m.id for m in expected.milestones]
    assert [m.conditions for m in loaded.milestones] == [m.conditions for m in expected.milestones]
    assert sorted(p.relative_to(ws) for p in ws.rglob("*")) == [Path("plan.toml")]
    d = plandoc(result)
    assert d["ok"] is True
    assert d["path"] == str(out)
    assert d["milestone_count"] == 2
    assert d["cost_usd"] > 0

    (ws / "a.txt").write_text("ok", encoding="utf-8")
    scripted.script.extend(["Final Answer: A", "Final Answer: B"])
    run = run_cli([
        "project", "run", str(out), "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    assert run.exit_code == 0


def test_plan_repair_then_ok(scripted, ws, cfg_file):
    scripted.script.extend(["not json", json.dumps(VALID)])
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    plandoc(result)
    assert result.exit_code == 0
    assert len(scripted.calls) == 2
    assert out.exists()


def test_plan_invalid_twice(scripted, ws, cfg_file):
    scripted.script.extend(["not json", '{"goal": "g", "milestones": []}', "unused"])
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    d = plandoc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert "no milestones" in d["errors"][0]
    assert not out.exists()
    assert len(scripted.calls) == 2


def test_plan_fenced_json(scripted, ws, cfg_file):
    scripted.script.append("```json\n" + json.dumps(VALID) + "\n```")
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    plandoc(result)
    assert result.exit_code == 0


def test_plan_cost_cap_exit_4(scripted, ws, cfg_file):
    scripted.script.append(json.dumps(VALID))
    out = ws / "plan.toml"
    result = run_cli([
        "project", "plan", "g", "-o", str(out), "--max-cost", "0", "--json", *base(ws, cfg_file),
    ])
    d = plandoc(result)
    assert result.exit_code == 4
    assert d["stop_reason"] == "budget_exceeded"
    assert len(scripted.calls) == 0
    assert not out.exists()


def test_plan_provider_account_error_exit_2(scripted, ws, cfg_file):
    def boom(req):
        raise ProviderAccountError(402, "no credit")

    scripted.script.append(boom)
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    d = plandoc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert d["errors"]
    assert not out.exists()


def test_plan_missing_output_and_human_mode(scripted, ws, cfg_file):
    result = run_cli(["project", "plan", "g", "--json", *base(ws, cfg_file)])
    d = plandoc(result)
    assert result.exit_code == 2
    assert "missing -o/--output" in d["errors"][0]

    scripted.script.append(json.dumps(VALID))
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), *base(ws, cfg_file)])
    assert result.exit_code == 0
    assert result.stdout == str(out) + "\n"


def test_plan_json_no_stray_stdout(scripted, ws, cfg_file, monkeypatch):
    original = planner_mod.plan_messages

    def noisy(goal, max_milestones):
        print("STRAY")
        return original(goal, max_milestones)

    monkeypatch.setattr(planner_mod, "plan_messages", noisy)
    scripted.script.append(json.dumps(VALID))
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    plandoc(result)
    assert result.exit_code == 0
    assert "STRAY" in result.stderr


def test_run_with_conditions_gate_failed_cli(scripted, ws, cfg_file, tmp_path):
    plan = write_gate_plan(tmp_path)
    scripted.script.extend(["Final Answer: A", "Final Answer: B1", "Final Answer: B2"])
    result = run_cli([
        "project", "run", str(plan), "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "gate_failed"
    assert statuses(d) == ["completed", "failed", "pending"]
    assert d["milestones"][1]["gate"] == {
        "attempts": 2,
        "passed": False,
        "failed_condition": f"command `{COND}`",
    }
    assert "gate" not in d["milestones"][0]
    assert task_calls(scripted, "gamma-task") == 0

    (ws / "done.txt").write_text("ok", encoding="utf-8")
    scripted.script[:] = ["Final Answer: B3", "Final Answer: C"]
    result = run_cli([
        "project", "resume", d["run_id"], "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    assert d["milestones"][1]["gate"]["attempts"] == 1
    assert d["milestones"][1]["gate"]["passed"] is True


def test_gate_retries_zero_cli(scripted, ws, cfg_file, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n[project]\ngate_retries = 0\n", name="cora0.toml")
    plan = write_gate_plan(tmp_path)
    scripted.script.extend(["Final Answer: A", "Final Answer: B1"])
    result = run_cli([
        "project", "run", str(plan), "--approval", "auto", "--headless", "--json", *base(ws, cfg),
    ])
    d = pdoc(result)
    assert result.exit_code == 1
    assert d["milestones"][1]["gate"]["attempts"] == 1
    assert len(scripted.calls) == 2


@pytest.mark.parametrize(
    "cond,problem",
    [
        ({"kind": "http"}, "unknown kind 'http'"),
        ({"kind": "command"}, "'cmd' must be a non-empty string"),
        ({"kind": "file_exists", "path": "/etc/x"}, "relative to the workspace"),
        ({"kind": "file_exists", "path": "../x"}, "relative to the workspace"),
        ({"kind": "command", "cmd": "true", "extra": 1}, "unknown key 'extra'"),
    ],
)
def test_invalid_condition_cli(scripted, ws, cfg_file, tmp_path, cond, problem):
    inline = ", ".join(f"{k} = {json.dumps(v)}" for k, v in cond.items())
    text = (
        'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "a"\ntask = "x"\n'
        f"conditions = [ {{ {inline} }} ]\n"
    )
    plan = tmp_path / "bad.toml"
    plan.write_text(text, encoding="utf-8")
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 2
    assert problem in d["errors"][0]
    assert not (ws / ".cora" / "projects").exists()


def test_policy_denied_condition_cli(scripted, ws, cfg_file, tmp_path):
    (tmp_path / "secret.txt").write_text("TOPSECRET", encoding="utf-8")
    text = (
        'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "a"\ntask = "alpha-task"\n'
        'conditions = [ { kind = "command", cmd = "cat ../secret.txt" } ]\n'
    )
    plan = tmp_path / "secret_plan.toml"
    plan.write_text(text, encoding="utf-8")
    scripted.script.extend(["Final Answer: A1", "Final Answer: A2"])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "gate_failed"
    checkpoint_text = (ws / ".cora" / "projects" / d["run_id"] / "checkpoint.json").read_text(
        encoding="utf-8")
    assert "TOPSECRET" not in result.stdout
    assert "TOPSECRET" not in result.stderr
    assert "TOPSECRET" not in checkpoint_text
    for req in scripted.calls:
        for m in req.messages:
            assert "TOPSECRET" not in m.content


def test_gate_retry_cost_cap_exit_4(scripted, ws, cfg_file, tmp_path):
    text = (
        'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "one"\ntask = "alpha-task"\n'
        "conditions = [ { kind = \"command\", cmd = " + json.dumps(COND) + " } ]\n"
    )
    plan = tmp_path / "cap.toml"
    plan.write_text(text, encoding="utf-8")
    scripted.script.extend([
        R("Final Answer: A", 0.3),
        R(act("list_files", {"path": "."}), 0.3),
        R("Final Answer: never", 0.01),
    ])
    result = run_cli([
        "project", "run", str(plan), "--approval", "auto", "--headless", "--json",
        "--max-cost", "0.5", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 4
    assert d["stop_reason"] == "budget_exceeded"
    assert d["budget"]["used"]["cost_usd"] == pytest.approx(0.6)
    cp = cp_json(ws, d["run_id"])
    assert cp["milestones"]["m1"]["status"] != "completed"
    assert cp["milestones"]["m1"]["gate"]["attempts"] == 1

    (ws / "done.txt").write_text("ok", encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    result = run_cli([
        "project", "resume", d["run_id"], "--approval", "auto", "--headless", "--json",
        "--max-cost", "5", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0


def test_run_goal_plans_then_runs(scripted, ws, cfg_file, tmp_path):
    scripted.script.extend([
        R(json.dumps(TWO_PLAIN), 0.01),
        R("Final Answer: A", 0.02),
        R("Final Answer: B", 0.03),
    ])
    out = tmp_path / "out.toml"
    result = run_cli([
        "project", "run", "--goal", "g", "--headless", "--json", "-o", str(out),
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    assert d["cost_usd"] == pytest.approx(0.06)
    assert d["budget"]["used"]["cost_usd"] == pytest.approx(0.06)
    plan_copy = ws / ".cora" / "projects" / d["run_id"] / "plan.toml"
    assert load_plan(plan_copy) == load_plan(out)
    cp = cp_json(ws, d["run_id"])
    assert cp["planning"]["cost_usd"] == pytest.approx(0.01)


def test_run_goal_cost_includes_planning_on_trip(scripted, ws, cfg_file):
    scripted.script.append(json.dumps(TWO_PLAIN))
    result = run_cli([
        "project", "run", "--goal", "g", "--headless", "--json", "--max-cost", "0",
        "-o", str(ws / "out.toml"), *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 4
    assert len(scripted.calls) == 0
    assert d["run_id"] is None


def test_run_goal_and_plan_conflict(scripted, ws, cfg_file, tmp_path):
    plan = tmp_path / "plan.toml"
    plan.write_text('goal = "g"\n', encoding="utf-8")
    result = run_cli([
        "project", "run", str(plan), "--goal", "g", "--headless", "--json", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert "either a plan file or --goal" in d["errors"][0]

    result = run_cli([
        "project", "run", str(plan), "-o", str(tmp_path / "x.toml"), "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert "requires --goal" in d["errors"][0]


def test_run_neither_plan_nor_goal(scripted, ws, cfg_file):
    result = run_cli(["project", "run", "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 2
    assert "no plan file given" in d["errors"][0]


def test_run_goal_planning_failure_exit_2(scripted, ws, cfg_file):
    scripted.script.extend(["x", "y"])
    result = run_cli([
        "project", "run", "--goal", "g", "--headless", "--json", "-o", str(ws / "out.toml"),
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert d["run_id"] is None
    assert "after one repair attempt" in d["errors"][0]
    assert not (ws / ".cora" / "projects").exists()


def test_project_help_lists_plan():
    result = run_cli(["project", "--help"])
    assert result.exit_code == 0
    assert "plan" in result.stdout
    assert "run" in result.stdout
    assert "resume" in result.stdout

