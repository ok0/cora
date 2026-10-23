from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import pytest

from cora.bench import e2e
from cora.bench.e2e import E2ETask, GraderResult, agent_prompt, load_e2e_tasks
from cora.core.checks import PYTEST_COMMAND, detect_check_command

pytestmark = pytest.mark.slow

HARD_F = ("e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06")
HARD_X = ("e2e_hx1", "e2e_hx2")
HARD = HARD_F + HARD_X
VISIBLE = HARD_F + ("e2e_hx2",)
SMOKE = (
    "e2e_todo_cli", "e2e_text_stats", "e2e_rest_notes", "e2e_md_to_html", "e2e_refactor_inventory",
)
FORBIDDEN_NET = (
    "socket", "ssl", "urllib", "http.client", "httpx", "requests", "ftplib", "smtplib",
    "telnetlib", "xmlrpc",
)
ALL = [t.id for t in load_e2e_tasks()]


def _task(tid: str) -> E2ETask:
    return next(t for t in load_e2e_tasks() if t.id == tid)


def _files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _changed(task: E2ETask) -> set[str]:
    template = _files(task.template_dir)
    changed = {
        rel
        for rel, data in _files(task.reference_dir).items()
        if template.get(rel) != data
    }
    return changed | set(task.reference_delete)


def _graded(task: E2ETask, tmp: Path, variant: str) -> tuple[Path, GraderResult, float]:
    ws = e2e.prepare_workspace(task, tmp / variant)
    assert ws.resolve().is_relative_to(tmp.resolve())
    assert not ws.resolve().is_relative_to(Path(str(e2e.e2e_tasks_dir())).resolve())
    if variant == "reference":
        e2e.apply_reference(task, ws)
    start = time.monotonic()
    result = e2e.run_grader(task, ws, tmp / variant / "harness")
    elapsed = time.monotonic() - start
    return ws, result, elapsed


def _visible_tests(ws: Path) -> set[str]:
    names: set[str] = set()
    for path in ws.rglob("test_*.py"):
        if ".cora_grader" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def _pytest(ws: Path) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ws,
        env={**e2e.grader_env(ws), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    ).returncode


def _net_imports(paths: list[Path]) -> list[str]:
    found: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith(FORBIDDEN_NET):
                    found.append(f"{path}: imports {name}")
    return found


def test_hard_set_present() -> None:
    assert set(HARD) <= set(ALL)
    assert [i for i in ALL if i.startswith("e2e_h")] == list(HARD)
    assert 4 <= len(HARD_F)
    assert len(HARD) <= 10
    assert ALL[:5] == list(SMOKE)


@pytest.mark.parametrize("tid", ALL)
def test_task_invariants(tid: str, tmp_path: Path, no_network: list[str]) -> None:
    task = _task(tid)
    _, template, t_elapsed = _graded(task, tmp_path, "template")
    assert template.status == "ok", template.reason
    assert not template.full_pass
    _, reference, r_elapsed = _graded(task, tmp_path, "reference")
    assert reference.status == "ok", reference.reason
    assert reference.full_pass
    assert t_elapsed < task.grader_timeout_s
    assert r_elapsed < task.grader_timeout_s
    assert no_network == []
    py_files = sorted(
        p
        for d in (task.grader_dir, task.template_dir, task.reference_dir)
        for p in d.rglob("*.py")
    )
    assert _net_imports(py_files) == []


@pytest.mark.parametrize("tid", HARD)
def test_hard_limits(tid: str) -> None:
    task = _task(tid)
    assert task.difficulty in ("medium", "hard")
    assert 25 <= task.max_iterations <= 30
    assert task.wall_s >= 2400
    assert task.cost_usd >= 0.05
    assert task.grader_visibility == "hidden"


@pytest.mark.parametrize("tid", HARD_F)
def test_f_task_shape(tid: str, tmp_path: Path) -> None:
    task = _task(tid)
    assert len(_changed(task)) >= 3
    _, reference, _ = _graded(task, tmp_path, "reference")
    assert len(reference.checks) >= 5
    ws_t = e2e.prepare_workspace(task, tmp_path / "shape")
    assert detect_check_command(ws_t) == PYTEST_COMMAND


@pytest.mark.parametrize("tid", VISIBLE)
def test_visible_suite_is_strict_subset(tid: str, tmp_path: Path) -> None:
    task = _task(tid)
    ws_t = e2e.prepare_workspace(task, tmp_path / "template")
    names = {n.removeprefix("test_") for n in _visible_tests(ws_t)}
    _, reference, _ = _graded(task, tmp_path, "reference")
    hidden = {c["name"] for c in reference.checks}
    assert names
    assert names < hidden
    assert _pytest(ws_t) != 0
    ws_r = tmp_path / "reference" / "ws"
    assert _pytest(ws_r) == 0


@pytest.mark.parametrize("tid", HARD_X)
def test_x_task_exploration(tid: str, tmp_path: Path) -> None:
    task = _task(tid)
    ws_t = e2e.prepare_workspace(task, tmp_path / "template")
    files = _files(ws_t)
    assert len(files) >= 30
    assert sum(len(v) for v in files.values()) >= 20 * 1024
    exploration = json.loads((task.grader_dir / "exploration.json").read_text(encoding="utf-8"))
    sources = exploration["sources"]
    assert isinstance(sources, list) and sources
    assert all(isinstance(s, str) for s in sources)
    for s in sources:
        assert (task.template_dir / s).is_file()
    prompt = agent_prompt(task)
    req = task.requirements_path.read_text(encoding="utf-8")
    for s in sources:
        for text in (prompt, req):
            assert s not in text
            assert PurePosixPath(s).name not in text
    assert set(task.required_files).isdisjoint(sources)
    _, reference, _ = _graded(task, tmp_path, "reference")
    assert len(reference.checks) >= 5
    if tid == "e2e_hx1":
        assert len(sources) >= 3
        assert detect_check_command(ws_t) is None
        assert task.required_files == ("ANSWERS.json",)
    if tid == "e2e_hx2":
        assert len(sources) >= 4
        assert set(sources) == _changed(task)
        assert detect_check_command(ws_t) == PYTEST_COMMAND
