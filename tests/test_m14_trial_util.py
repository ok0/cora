from __future__ import annotations

from cora.bench import e2e
from e2e_trial_util import grade, leakcheck, prepare


def test_prepare_grade_reference(tmp_path):
    task = e2e.select_e2e_tasks(["e2e_todo_cli"])[0]
    ws = prepare("e2e_todo_cli", tmp_path)
    e2e.apply_reference(task, ws)
    assert leakcheck("e2e_todo_cli", ws, pre_grade=True) == []
    assert grade("e2e_todo_cli", ws, tmp_path / "grade")["full_pass"] is True
    assert (ws / ".cora_grader").is_dir()
    assert leakcheck("e2e_todo_cli", ws) == []


def test_leakcheck_flags_grader_path(tmp_path):
    task = e2e.select_e2e_tasks(["e2e_todo_cli"])[0]
    ws = prepare("e2e_todo_cli", tmp_path)
    (ws / ".cora").mkdir(exist_ok=True)
    (ws / ".cora" / "x.log").write_text(str(task.grader_dir), encoding="utf-8")
    assert leakcheck("e2e_todo_cli", ws) == [".cora/x.log"]


def test_leakcheck_pre_grade_flags_grader_dir(tmp_path):
    ws = prepare("e2e_todo_cli", tmp_path)
    (ws / ".cora_grader").mkdir()
    (ws / ".cora_grader" / "grade.py").write_text(".cora_grader", encoding="utf-8")
    assert leakcheck("e2e_todo_cli", ws, pre_grade=True) == [".cora_grader"]
    assert leakcheck("e2e_todo_cli", ws) == []
    (ws / "notes.txt").write_text("see .cora_grader/grade.py", encoding="utf-8")
    assert leakcheck("e2e_todo_cli", ws) == ["notes.txt"]
