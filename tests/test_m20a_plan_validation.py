from __future__ import annotations

import json
from pathlib import Path

import pytest

from cora.bench import e2e
from cora.core.config import load_config
from cora.core.milestones import load_plan
from cora.core.planner import validate_plan_policy
from cora.core.policy import PolicyGate, load_policy, planning_policy

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "tests" / "fixtures" / "m20" / "artifacts"
PLANQ = ROOT / "tests" / "fixtures" / "m20" / "planq.jsonl"
TASKS = ("e2e_h01", "e2e_h02", "e2e_h03", "e2e_h05", "e2e_h06")
SKIP_REASON = "R1 blocked: M20 artifacts directory is missing"


def _fix2_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in PLANQ.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("label") == "deepseek-fix2":
            rows[row["task"]] = row
    return rows


def _setup(task_id: str, tmp_path: Path):
    task = e2e.select_e2e_tasks([task_id])[0]
    ws = e2e.prepare_workspace(task, tmp_path / task_id)
    e2e.apply_reference(task, ws)
    cfg = load_config(ARTIFACTS / "cora-m20-deepseek.toml")
    pol = planning_policy(cfg.policy, ws, "policy")
    assert pol is not None
    plan = load_plan(ARTIFACTS / "p1c" / task_id / "plan.toml")
    return cfg, ws, pol, plan


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason=SKIP_REASON)
@pytest.mark.parametrize("task_id", TASKS)
def test_validation_matches_fix2_counts(task_id, tmp_path):
    cfg, ws, pol, plan = _setup(task_id, tmp_path)
    issues = validate_plan_policy(plan, pol)
    row = _fix2_rows()[task_id]
    checks = [i for i in issues if i.field == "check"]
    conds = [i for i in issues if i.field.startswith("conditions[")]
    assert len(checks) == row["checks_blocked"]
    assert len(conds) == row["conditions_blocked"]


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason=SKIP_REASON)
@pytest.mark.parametrize("task_id", TASKS)
def test_each_check_matches_real_gate(task_id, tmp_path):
    cfg, ws, pol, plan = _setup(task_id, tmp_path)
    flagged = {(i.milestone_id, i.field) for i in validate_plan_policy(plan, pol)}
    gate = PolicyGate(load_policy(cfg.policy, ws), ws)
    for m in plan.milestones:
        if m.check:
            expected = gate.check("run_shell", {"command": m.check}, "policy").blocked
            assert ((m.id, "check") in flagged) == expected


@pytest.mark.skipif(not ARTIFACTS.is_dir(), reason=SKIP_REASON)
def test_total_check_issues_14_of_28(tmp_path):
    flagged_total = 0
    checks_total = 0
    for task_id in TASKS:
        cfg, ws, pol, plan = _setup(task_id, tmp_path / task_id)
        checks_total += sum(1 for m in plan.milestones if m.check)
        flagged_total += sum(
            1 for i in validate_plan_policy(plan, pol) if i.field == "check"
        )
    assert checks_total == 28
    assert flagged_total == 14
