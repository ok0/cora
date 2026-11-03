from __future__ import annotations

import hashlib
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
    DEADLINE_LINES,
    DEADLINE_TOML,
    M20B_POLICY_BLOCK,
    ROOT,
    check_conditions,
    checkq_row,
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
            "checks_total": 0,
            "check_runnable": 0,
            "checks_blocked": 0,
            "checks_pass_ref": 0,
            "all_checks_runnable": True,
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


def test_make_config_deadline_variant(tmp_path):
    out = tmp_path / "d.toml"
    make_config(DEEPSEEK, out, variant="deadline")
    cfg = load_config(out)
    assert cfg.providers["openrouter"]["request_deadline_s"] == 300
    assert cfg.providers["openrouter"]["timeout_s"] == 300
    assert cfg.agent.call_timeout_s == 960
    assert HeuristicRouter(cfg).model_for("cheap").id == DEEPSEEK
    base = (m20_trial.m20_base_text() + m20_trial.M20B_POLICY_BLOCK).splitlines()
    gen = out.read_text(encoding="utf-8").splitlines()
    added = set(gen) - set(base)
    assert len(added) == 4
    assert sum(1 for line in added if line.startswith(DEADLINE_LINES)) == 3
    assert sum(1 for line in added if line.startswith(f'pin = "{DEEPSEEK}"')) == 1
    removed = set(base) - set(gen)
    assert len(removed) == 3
    assert all(
        any(line.startswith(p) for line in removed)
        for p in ("timeout_s = 120", "request_deadline_s = 90", "call_timeout_s = 300")
    )


def test_make_config_deadline_matches_m19(tmp_path):
    out = tmp_path / "d.toml"
    make_config(DEEPSEEK, out, variant="deadline")
    gen = [
        line
        for line in out.read_text(encoding="utf-8").splitlines()
        if not line.startswith("pin = ")
    ]
    block = M20B_POLICY_BLOCK.splitlines()
    assert gen[-len(block) :] == block
    gen = gen[: -len(block)]
    assert gen == DEADLINE_TOML.read_text(encoding="utf-8").splitlines()


def test_make_config_prompt_rules(tmp_path):
    out = tmp_path / "p.toml"
    make_config(GEMINI, out, prompt_rules=True)
    assert load_config(out).policy.prompt_rules is True
    gen = out.read_text(encoding="utf-8").splitlines()
    base = (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines()
    added = [line for line in gen if line not in base]
    removed = [line for line in base if line not in gen]
    assert len(added) == 2
    assert added[0].startswith(f'pin = "{GEMINI}"')
    assert added[1].startswith("prompt_rules = true")
    assert len(removed) == 1
    assert removed[0].startswith("prompt_rules = false")


def test_m20_base_text_is_prereg():
    digest = hashlib.sha256(m20_trial.m20_base_text().encode()).hexdigest()
    assert digest == "7704ace8db75918f63e2f4df8e6b7d009cabf3d73cc98e0165f6c677abcd883a"


def test_make_config_unknown_variant(tmp_path):
    with pytest.raises(SystemExit) as exc:
        make_config(DEEPSEEK, tmp_path / "x.toml", variant="x")
    assert exc.value.code == 2


def test_config_cli_variant(tmp_path, capsys):
    out = tmp_path / "d.toml"
    assert m20_trial.main(["config", DEEPSEEK, str(out), "--variant", "deadline"]) == 0
    printed = capsys.readouterr().out.strip()
    assert printed == hashlib.sha256(out.read_bytes()).hexdigest()


def test_check_runnable_on_reference(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    plan = ProjectPlan(
        goal="g",
        milestones=(
            Milestone(
                id="m1",
                title="t",
                task="do it",
                check="python -m py_compile csvreport/parser.py",
            ),
            Milestone(
                id="m2",
                title="t",
                task="do it",
                check="All required files exist with correct module layout",
            ),
            Milestone(id="m3", title="t", task="do it"),
        ),
    )
    plan_path = tmp_path / "plan.toml"
    plan_path.write_text(plan_to_toml(plan), encoding="utf-8")
    cfg_path = tmp_path / "cfg.toml"
    make_config(DEEPSEEK, cfg_path)
    result = check_conditions("e2e_h01", plan_path, cfg_path)
    assert result["checks_total"] == 2
    assert result["check_runnable"] == 1
    assert result["checks_blocked"] == 1
    assert result["checks_pass_ref"] == 1
    assert result["all_checks_runnable"] is False
    assert result["check_details"][1]["blocked"] is True
    assert result["conditions_total"] == 0
    row = checkq_row("e2e_h01", plan_path, cfg_path, "deepseek-fix1")
    assert row["label"] == "deepseek-fix1"
    assert row["checks_total"] == 2
    assert row["check_runnable"] == 1
    assert row["checks_blocked"] == 1
    assert row["checks_pass_ref"] == 1


def test_run_row_rerun(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(m20_trial, "OUT_ROOT", tmp_path / "out")
    work = tmp_path / "w"
    work.mkdir()
    ws = m20_trial.prepare("e2e_h01", work)
    row = run_row("e2e_h01", ws, _outcome(), "deepseek", 2, 1, rerun_of="e2e_h01-r2")
    assert row["rerun_of"] == "e2e_h01-r2"
    assert row["interventions"] == 1
    assert (tmp_path / "out" / "deepseek" / "e2e_h01-r2-rerun" / "outcome.json").exists()
    assert not (tmp_path / "out" / "deepseek" / "e2e_h01-r2").exists()


def _rr(
    task: str,
    run: int,
    completed: bool,
    cost: float,
    label: str,
    stop: str,
    **extra,
) -> dict:
    row = _run_row(task, run, completed, cost, label=label)
    row["stop_reason"] = stop
    row.update(extra)
    return row


def test_summary_superseded_and_labels():
    runs = [
        _rr("e2e_h01", 0, False, 0.01, "deepseek", "policy_blocked"),
        _rr("e2e_h01", 1, False, 0.02, "deepseek", "budget_exceeded"),
        _rr("e2e_h01", 2, False, 0.0, "deepseek", "error"),
        _rr("e2e_h01", 2, True, 0.05, "deepseek", "final_answer", rerun_of="e2e_h01-r2"),
        _rr("e2e_h01", 0, True, 0.03, "deepseek-v2", "final_answer"),
        _rr("e2e_h01", 1, False, 0.04, "deepseek-v2", "budget_exceeded"),
        _rr("e2e_h01", 2, True, 0.05, "deepseek-v2", "final_answer"),
    ]
    planq = [
        {
            "task": "e2e_h01",
            "label": "deepseek",
            "plan_quality": "first_try",
            "first_reply_strict": True,
            "milestones": 1,
            "conditions_total": 0,
            "conditions_executable": 0,
            "conditions_pass_ref": 0,
            "cost_usd": 0.01,
        },
        {
            "task": "e2e_h01",
            "label": "deepseek-fix1",
            "plan_quality": "first_try",
            "first_reply_strict": True,
            "milestones": 1,
            "conditions_total": 0,
            "conditions_executable": 0,
            "conditions_pass_ref": 0,
            "cost_usd": 0.01,
            "checks_total": 3,
            "check_runnable": 3,
        },
        {
            "task": "e2e_h01",
            "label": "deepseek-fix2",
            "plan_quality": "first_try",
            "first_reply_strict": True,
            "milestones": 1,
            "conditions_total": 0,
            "conditions_executable": 0,
            "conditions_pass_ref": 0,
            "cost_usd": 0.01,
            "checks_total": 4,
            "check_runnable": 4,
        },
    ]
    checks = [{"task": "e2e_h01", "label": "deepseek", "checks_total": 8, "check_runnable": 0}]
    text = summary(planq, runs, None, checks_rows=checks)
    lines = text.splitlines()
    assert any("error (superseded)" in line for line in lines)
    assert any("(rerun e2e_h01-r2)" in line for line in lines)
    assert "### (2) Per-run (deepseek)" in text
    assert "### (2) Per-run (deepseek-v2)" in text
    assert "(pre-fix planner prompt)" in text
    assert "(post-fix planner prompt, R11 round 1)" in text
    assert "(post-fix planner prompt, R11 round 2)" in text
    assert any("| 4/4 |" in line for line in text.splitlines())
    assert any("| 0/8 |" in line for line in lines)
    assert any("| 3/3 |" in line for line in lines)
    ds_block = text.split("### (2) Per-run (deepseek-v2)")[0]
    assert any(line.startswith("| e2e_h01 | 1/3 |") for line in ds_block.splitlines())
    assert "| e2e_h03 |" not in ds_block
    v2_block = text.split("### (2) Per-run (deepseek-v2)")[1]
    assert any(line.startswith("| e2e_h01 | 2/3 |") for line in v2_block.splitlines())
    assert any(line.startswith("| e2e_h03 | 0/0 |") for line in v2_block.splitlines())
    assert any(line.startswith("| e2e_n08 | 0/0 |") for line in v2_block.splitlines())


def test_planq_row_policy_fields(tmp_path, monkeypatch):
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
            "checks_total": 0,
            "check_runnable": 0,
            "checks_blocked": 0,
            "checks_pass_ref": 0,
            "all_checks_runnable": True,
        },
    )
    records = tmp_path / "rec"
    text = _plan_json()
    _write_record(records, "0001.json", 2, text)
    _write_record(records, "0002.json", 4, text)
    pp = {
        "issues": 3,
        "repaired": 2,
        "dropped": 1,
        "rounds": 1,
        "ungated": ["m2"],
        "policy_dropped": [
            {"milestone": "m2", "field": "check", "command": "cd x", "rule": "confine:cd"}
        ],
    }
    row = planq_row(
        "e2e_h01",
        _outcome(plan_policy=pp),
        tmp_path / "plan.toml",
        records,
        "deepseek",
        tmp_path / "c.toml",
    )
    assert row["plan_quality"] == "first_try"
    assert row["policy_dropped"] == 1
    assert row["ungated"] == ["m2"]
    assert row["policy_issues"] == 3
    assert row["policy_repaired"] == 2
    assert row["policy_rounds"] == 1
    assert row["policy_first_try"] is False


def test_summary_policy_columns_only_when_present():
    base = {
        "task": "e2e_h01",
        "label": "deepseek-v2",
        "plan_quality": "first_try",
        "first_reply_strict": True,
        "milestones": 1,
        "conditions_total": 0,
        "conditions_executable": 0,
        "conditions_pass_ref": 0,
        "cost_usd": 0.01,
    }
    with_policy = {
        **base,
        "label": "deepseek-fix3",
        "policy_issues": 1,
        "policy_repaired": 0,
        "policy_dropped": 1,
        "ungated": ["m1"],
    }
    text = summary([with_policy], [], None)
    assert "ungated milestones" in text
    assert "| 1/0/1 | m1 |" in text
    old_rows = m20_trial._read_jsonl(ROOT / "tests" / "fixtures" / "m20" / "planq.jsonl")
    assert "ungated milestones" not in summary(old_rows, [], None)
    assert "ungated milestones" in summary([base, with_policy], [], None)
