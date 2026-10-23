from __future__ import annotations

import json
from pathlib import Path

import pytest

import m20_trial
from cora.bench import e2e
from cora.bench.stats import wilson_interval
from cora.core.config import load_config
from cora.core.milestones import Condition, Milestone, ProjectPlan, plan_to_toml
from cora.core.router import HeuristicRouter
from m20_trial import (
    ROOT,
    check_conditions,
    event_hits,
    goal_text,
    keygrep,
    make_config,
    planq_row,
    run_row,
    summary,
)

DEEPSEEK = "deepseek/deepseek-v3.2"
GEMINI = "gemini-3.5-flash-lite"


def _plan_json(conditions: tuple[Condition, ...] = ()) -> str:
    plan = ProjectPlan(
        goal="g",
        milestones=(Milestone(id="m1", title="t", task="do it", conditions=conditions),),
    )
    return json.dumps(plan.to_dict())


def _write_record(records: Path, name: str, n_messages: int, text: str) -> None:
    records.mkdir(parents=True, exist_ok=True)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    messages += [{"role": "assistant", "content": "a"}, {"role": "user", "content": "r"}][
        : n_messages - 2
    ]
    entry = {"request": {"messages": messages}, "response": {"text": text}}
    (records / name).write_text(json.dumps(entry), encoding="utf-8")


def _outcome(**kw) -> dict:
    base = {
        "ok": True,
        "exit_code": 0,
        "stop_reason": "final_answer",
        "cost_usd": 0.01,
        "models": [DEEPSEEK],
        "errors": [],
        "policy": None,
        "milestone_count": 1,
    }
    base.update(kw)
    return base


def test_make_config_pins_model(tmp_path):
    out = tmp_path / "c.toml"
    make_config(DEEPSEEK, out)
    cfg = load_config(out)
    router = HeuristicRouter(cfg)
    assert router.route("refactor the whole parser module").model.id == DEEPSEEK
    assert router.model_for("cheap").id == DEEPSEEK


def test_make_config_only_adds_pin(tmp_path):
    out = tmp_path / "c.toml"
    make_config(DEEPSEEK, out)
    base = (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines()
    gen = out.read_text(encoding="utf-8").splitlines()
    added = [line for line in gen if line not in base]
    assert len(added) == 1
    assert added[0].startswith(f'pin = "{DEEPSEEK}"')
    assert all(line in gen for line in base)
    assert len(gen) == len(base) + 1


def test_make_config_gemini(tmp_path):
    out = tmp_path / "g.toml"
    make_config(GEMINI, out)
    gen = out.read_text(encoding="utf-8").splitlines()
    base = (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines()
    added = [line for line in gen if line not in base]
    assert len(added) == 1
    assert added[0].startswith(f'pin = "{GEMINI}"')
    assert len(gen) == len(base) + 1


def test_make_config_unknown_model_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        make_config("x/unknown", tmp_path / "u.toml")
    assert exc.value.code == 2


def test_make_config_refuses_repo_path():
    out = ROOT / "tests" / "m20_should_not_exist.toml"
    with pytest.raises(SystemExit) as exc:
        make_config(DEEPSEEK, out)
    assert exc.value.code == 2
    assert not out.exists()


@pytest.mark.parametrize("task_id", ["e2e_h01", "e2e_h03", "e2e_n08"])
def test_goal_text(task_id):
    task = e2e.select_e2e_tasks([task_id])[0]
    text = goal_text(task_id)
    assert all(f in text for f in task.required_files)
    assert task.requirements_path.read_text(encoding="utf-8") in text
    pre = text.split("--- REQUIREMENTS.md ---", 1)[0].lower()
    for word in ("grader", "reference", ".cora_grader", "hidden"):
        assert word not in pre
    for word in ("grader", ".cora_grader", "grade.py"):
        assert word not in text.lower()


def test_planner_calls_classification(tmp_path, monkeypatch):
    monkeypatch.setattr(
        m20_trial,
        "check_conditions",
        lambda *a, **k: {
            "conditions_total": 0,
            "conditions_executable": 0,
            "conditions_pass_ref": 0,
            "all_executable": True,
            "all_pass_ref": True,
            "conditions_blocked": 0,
        },
    )
    plan_path = tmp_path / "plan.toml"
    cfg_path = tmp_path / "c.toml"
    text = _plan_json()

    one = tmp_path / "one"
    _write_record(one, "0001.json", 2, text)
    row = planq_row("e2e_h01", _outcome(), plan_path, one, "deepseek", cfg_path)
    assert row["plan_quality"] == "first_try"
    assert row["first_reply_strict"] is True

    two = tmp_path / "two"
    _write_record(two, "0001.json", 2, text)
    _write_record(two, "0002.json", 4, text)
    row = planq_row("e2e_h01", _outcome(), plan_path, two, "deepseek", cfg_path)
    assert row["plan_quality"] == "after_repair"

    bad = _outcome(
        ok=False,
        errors=["planner reply invalid after one repair attempt: x"],
    )
    row = planq_row("e2e_h01", bad, plan_path, two, "deepseek", cfg_path)
    assert row["plan_quality"] == "invalid"

    blocked = _outcome(ok=False, errors=["openrouter HTTP 503 UNAVAILABLE"])
    row = planq_row("e2e_h01", blocked, plan_path, two, "gemini-rehearsal", cfg_path)
    assert row["plan_quality"] == "blocked"


def test_check_conditions_on_reference(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    plan = ProjectPlan(
        goal="g",
        milestones=(
            Milestone(
                id="m1",
                title="t",
                task="do it",
                conditions=(
                    Condition(kind="file_exists", path="csvreport/cli.py"),
                    Condition(kind="command", cmd="python -m py_compile csvreport/parser.py"),
                    Condition(kind="command", cmd="definitely_not_a_cmd_m20"),
                    Condition(kind="command", cmd="cat ~/.ssh/id_rsa"),
                ),
            ),
        ),
    )
    plan_path = tmp_path / "plan.toml"
    plan_path.write_text(plan_to_toml(plan), encoding="utf-8")
    cfg_path = tmp_path / "cfg.toml"
    make_config(DEEPSEEK, cfg_path)
    result = check_conditions("e2e_h01", plan_path, cfg_path)
    assert result["conditions_total"] == 4
    assert result["conditions_executable"] == 2
    assert result["conditions_pass_ref"] == 2
    assert result["details"][1]["blocked"] is False
    assert result["conditions_blocked"] == 2
    cat = result["details"][3]
    assert cat["blocked"] is True
    assert cat["executable"] is False


def test_run_row_completed_on_reference(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(m20_trial, "OUT_ROOT", tmp_path / "out")
    task = e2e.select_e2e_tasks(["e2e_h01"])[0]
    work = tmp_path / "w"
    work.mkdir()
    ws = m20_trial.prepare("e2e_h01", work)
    e2e.apply_reference(task, ws)
    cp_dir = ws / ".cora" / "projects" / "r1"
    cp_dir.mkdir(parents=True)
    (cp_dir / "checkpoint.json").write_text(
        json.dumps({"planning": {"calls": 1}}), encoding="utf-8"
    )
    outcome = _outcome(
        run_id="r1",
        errors=[],
        milestones=[
            {
                "id": "m1",
                "status": "done",
                "gate": {"attempts": 1, "passed": True, "failed_condition": None},
            }
        ],
    )
    row = run_row("e2e_h01", ws, outcome, "deepseek", 1, 0)
    assert row["completed"] is True
    assert row["leaks"] == []
    assert row["error_run"] is False
    assert row["gate_failed"] is False
    assert row["plan_quality"] == "first_try"


def test_run_row_error_and_plan_failed(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(m20_trial, "OUT_ROOT", tmp_path / "out")
    work = tmp_path / "w"
    work.mkdir()
    ws = m20_trial.prepare("e2e_h01", work)
    err = _outcome(ok=False, stop_reason="error", exit_code=1, errors=["openrouter HTTP 500"])
    row = run_row("e2e_h01", ws, err, "deepseek", 1, 0)
    assert row["error_run"] is True
    failed = _outcome(
        ok=False,
        stop_reason="error",
        exit_code=1,
        errors=["planner reply invalid after one repair attempt: y"],
    )
    row = run_row("e2e_h01", ws, failed, "deepseek", 2, 0)
    assert row["error_run"] is False
    assert row["plan_quality"] == "failed"


def test_event_hits(tmp_path):
    ws = tmp_path / "ws"
    run = ws / ".cora" / "projects" / "r1"
    run.mkdir(parents=True)
    protected = str(Path(Path.home() / ".ssh").resolve())
    (run / "events.jsonl").write_text(
        json.dumps({"tool": "read", "path": protected})
        + "\n"
        + json.dumps({"tool": "read", "path": "src/ok.py"})
        + "\n",
        encoding="utf-8",
    )
    assert len(event_hits(ws)) == 1
    clean = tmp_path / "clean"
    clean_run = clean / ".cora" / "projects" / "r2"
    clean_run.mkdir(parents=True)
    (clean_run / "events.jsonl").write_text(json.dumps({"tool": "read"}) + "\n", encoding="utf-8")
    assert event_hits(clean) == []


def test_keygrep(tmp_path, monkeypatch):
    key = "sk-or-test-0123456789"
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    planted = tmp_path / "leak.txt"
    planted.write_text(f"token={key}", encoding="utf-8")
    clean = tmp_path / "clean.txt"
    clean.write_text("nothing here", encoding="utf-8")
    result = keygrep([tmp_path])
    assert str(planted) in result["matches"]
    assert str(clean) not in result["matches"]
    assert key not in json.dumps(result)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        keygrep([tmp_path])
    assert exc.value.code == 2


def _run_row(task: str, run: int, completed: bool, cost: float, label: str = "deepseek") -> dict:
    return {
        "task": task,
        "label": label,
        "run": run,
        "completed": completed,
        "stop_reason": "final_answer",
        "interventions": 0,
        "iterations": 10,
        "cost_usd": cost,
        "wall_s": 100.0,
        "plan_quality": "first_try",
        "gate_failed": False,
        "leaks": [],
        "protected_hits": [],
    }


def test_summary_tables(tmp_path):
    rows = [
        _run_row("e2e_h01", 1, True, 0.03),
        _run_row("e2e_h01", 2, True, 0.04),
        _run_row("e2e_h01", 3, False, 0.05),
        _run_row("e2e_n08", 1, True, 0.02),
        _run_row("e2e_n08", 2, False, 0.02),
    ]
    baseline = tmp_path / "base.toml"
    baseline.write_text("[tasks.e2e_h01]\nsolved = 1.0\nn = 3\ncost_usd = 0.08\n", encoding="utf-8")
    text = summary([], rows, baseline)
    lines = text.splitlines()
    wl = wilson_interval(2, 3)
    assert any(line.startswith("| e2e_h01 | 2/3 |") and f"{wl[0]:.3f}" in line for line in lines)
    assert any(line.startswith("| e2e_n08 |") and "no claim (n<3)" in line for line in lines)
    assert any("no baseline (not measured)" in line for line in lines)
    total = 0.03 + 0.04 + 0.05 + 0.02 + 0.02
    assert any(f"{total / 3:.4f}" in line and "| 3 | 5 |" in line for line in lines)
