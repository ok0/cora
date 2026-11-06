from __future__ import annotations

import json
import shutil
from pathlib import Path

import m22b_baseline as b
from cora.bench.e2e import load_e2e_tasks, prepare_workspace
from cora.bench.live_tasks import LIVE_TASKS, write_task_files
from cora.core.policy import PolicyEngine, PolicySettings
from cora.core.shellguard import PathGuard, default_protected


def _today() -> dict:
    return json.loads(b.TODAY.read_text(encoding="utf-8"))


def test_classification_covers_today():
    today = _today()
    assert today["default"] == today["strict"]
    assert len(today["default"]) == 46
    assert list(b.CLASSIFICATION) == today["default"]
    kinds = [kind for kind, _ in b.CLASSIFICATION.values()]
    assert kinds.count("neutral") == 25
    assert kinds.count("toolchain:python") == 21
    assert all(reason.strip() for _, reason in b.CLASSIFICATION.values())


def test_python_workspaces_keep_today_set(tmp_path: Path):
    today = _today()
    synthetic = b.build_workspaces(tmp_path / "syn")
    workspaces = [synthetic["python"], synthetic["python-wide"]]

    e2e_tasks = load_e2e_tasks()
    assert len(e2e_tasks) == 27
    for task in e2e_tasks:
        workspaces.append(prepare_workspace(task, tmp_path / task.id))

    assert len(LIVE_TASKS) == 11
    for t in LIVE_TASKS:
        root = tmp_path / "live" / t.id
        write_task_files(root, t.files)
        workspaces.append(root)

    for ws in workspaces:
        for profile in ("default", "strict"):
            assert b.effective(profile, ws) == tuple(today[profile]), (ws, profile)


def test_r2_intended_outcomes(tmp_path: Path):
    assert len(b.R2_ROWS) == 20
    assert all(row[3] == ("deny", "default") for row in b.R2_ROWS)
    for i, (run, tpl, cmd, intended) in enumerate(b.R2_ROWS):
        src = b.TEMPLATES / tpl / "template"
        assert src.is_dir(), run
        ws = tmp_path / str(i) / "ws"
        shutil.copytree(src, ws)
        for strict in (False, True):
            engine = PolicyEngine(
                PolicySettings(), PathGuard(ws, default_protected()), strict=strict
            )
            verdict = engine.evaluate("run_shell", {"command": cmd})
            assert (verdict.decision, verdict.rule) == intended, (run, cmd, strict)
