from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import m20_trial
from cora.bench import e2e
from cora.core import milestones as ms
from m20_trial import run_row

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "tests/fixtures/m20/artifacts"


def outcome(group, name):
    return json.loads((ART / group / name / "outcome.json").read_text("utf-8"))


def _str_constants(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for elt in node.elts:
            yield from _str_constants(elt)


def _compare_literals(path):
    tree = ast.parse(path.read_text("utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                found.update(_str_constants(comp))
    return found, tree


def test_trial_uses_core_done_status():
    assert m20_trial.DONE_STATUS is ms.DONE_STATUS == "completed"
    assert ms.DONE_STATUS in ms.STATUSES


def test_no_copied_status_literal():
    banned = {"done", "passed", "completed"}
    for rel in ("tests/m20_trial.py", "src/cora/core/milestones.py"):
        found, tree = _compare_literals(ROOT / rel)
        assert not (found & banned), rel
    tree = ast.parse((ROOT / "src/cora/core/milestones.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if node.value.value == "completed":
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                assert targets == ["DONE_STATUS"], targets
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "STATUSES":
                    assert "completed" not in set(_str_constants(node.value))


def test_milestones_done_grader_passed_real_outcome(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(m20_trial, "OUT_ROOT", tmp_path / "out")
    task = e2e.select_e2e_tasks(["e2e_h01"])[0]
    work = tmp_path / "w"
    work.mkdir()
    ws = m20_trial.prepare("e2e_h01", work)
    e2e.apply_reference(task, ws)
    out = outcome("v2", "e2e_h01-r2")
    row = run_row("e2e_h01", ws, out, "deepseek-v2", 2, 0)
    assert row["completed"] is True
    assert row["milestones_done"] == 2 == sum(
        m["status"] == ms.DONE_STATUS for m in out["milestones"]
    )
    assert row["milestones_total"] == 5
    assert row["stop_reason"] == "budget_exceeded"


def test_milestones_done_mid_milestone_stop():
    out = outcome("v2", "e2e_h01-r0")
    assert m20_trial.milestones_done(out["milestones"]) == 2 < len(out["milestones"]) == 5
    assert out["stop_reason"] == "budget_exceeded"
    assert out["milestones"][2]["status"] == "failed"


def test_recomputed_m20_counts():
    lines = (ROOT / "tests/fixtures/m20/runs.jsonl").read_text("utf-8").splitlines()
    rows = [json.loads(line) for line in lines[4:13]]
    assert all(r["label"] == "deepseek-v2" for r in rows)
    recomputed = [
        m20_trial.milestones_done(outcome("v2", f"{r['task']}-r{r['run']}")["milestones"])
        for r in rows
    ]
    assert recomputed == [2, 0, 2, 0, 0, 0, 0, 0, 0]
    assert all(r["milestones_done"] == 0 for r in rows)
    for r, count in zip(rows, recomputed, strict=True):
        if r["completed"]:
            out = outcome("v2", f"{r['task']}-r{r['run']}")
            assert count < len(out["milestones"])
            assert out["stop_reason"] == "budget_exceeded"


def test_m20c_docs_diagnosis_table():
    text = (ROOT / ".docs/bench-results.md").read_text("utf-8")
    header = re.search(
        r"^## M20c 결과 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", text, re.MULTILINE
    )
    assert header is not None
    section = text[header.start():]
    a_start = section.index("\n### (a)")
    b_start = section.index("\n### (b)", a_start)
    a_text = section[a_start:b_start]
    rows = [line for line in a_text.splitlines() if line.startswith("| e2e_")]
    assert len(rows) == 9
    for row in rows:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        assert len(cells) == 9
        assert cells[7] in {"(a)", "(b)", "(a)+(b)"}
        assert "tests/fixtures/m20/" in cells[8]
    assert "0.01092832844" in section
