from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from cora.bench import e2e
from cora.bench.e2e import load_e2e_tasks
from e2e_util import make_task

pytestmark = pytest.mark.slow


def _task(tmp_path: Path, grader_code: str, timeout_s: float = 5):
    root = tmp_path / "tasks"
    make_task(root, "e2e_g", grader_code, timeout_s=timeout_s)
    [task] = load_e2e_tasks(root)
    run = tmp_path / "run"
    run.mkdir(parents=True)
    return task, run


OK_LINE = 'print(json.dumps({"checks": [{"name": "a", "passed": True}]}))'


def test_crash(tmp_path: Path) -> None:
    task, run = _task(tmp_path, 'raise RuntimeError("x")\n')
    ws = e2e.prepare_workspace(task, run)
    result = e2e.run_grader(task, ws, run / "harness")
    assert result.status == "grader_error"
    assert result.score == 0.0
    assert "exited with code 1" in result.reason


def test_garbage(tmp_path: Path) -> None:
    task, run = _task(tmp_path, 'print("not json")\n')
    ws = e2e.prepare_workspace(task, run)
    result = e2e.run_grader(task, ws, run / "harness")
    assert result.status == "grader_error"
    assert "invalid grader output" in result.reason


def test_infinite_loop_and_children_killed(tmp_path: Path) -> None:
    grader = (
        "import subprocess, sys, time\n"
        'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
        'open("child.pid", "w").write(str(p.pid))\n'
        "while True: time.sleep(0.1)\n"
    )
    task, run = _task(tmp_path, grader, timeout_s=1)
    ws = e2e.prepare_workspace(task, run)
    started = time.monotonic()
    result = e2e.run_grader(task, ws, run / "harness")
    assert time.monotonic() - started < 10
    assert result.timed_out
    assert result.status == "grader_error"
    assert result.score == 0.0
    assert "timed out after 1s" in result.reason
    pid = int((ws / "child.pid").read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, "grader child process survived the kill"
        time.sleep(0.1)


def test_env_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-1234567890")
    grader = (
        "import json, os\n"
        "print(json.dumps({'checks': [\n"
        "    {'name': 'env', 'passed': True, 'detail': ','.join(sorted(os.environ))},\n"
        "    {'name': 'cwd', 'passed': True, 'detail': os.getcwd()},\n"
        "]}))\n"
    )
    task, run = _task(tmp_path, grader)
    ws = e2e.prepare_workspace(task, run)
    result = e2e.run_grader(task, ws, run / "harness")
    assert result.status == "ok"
    env_detail = result.checks[0]["detail"]
    assert "OPENROUTER_API_KEY" not in env_detail
    assert result.checks[1]["detail"]
    assert Path(result.checks[1]["detail"]).resolve() == ws.resolve()


def test_output_cap(tmp_path: Path) -> None:
    flood = "print('x' * 200000)\n"
    task, run = _task(tmp_path, "import json\n" + flood + OK_LINE + "\n")
    ws = e2e.prepare_workspace(task, run)
    result = e2e.run_grader(task, ws, run / "harness")
    assert result.status == "ok"
    assert result.output_truncated

    task, run = _task(tmp_path / "second", flood)
    ws = e2e.prepare_workspace(task, run)
    result = e2e.run_grader(task, ws, run / "harness")
    assert result.status == "grader_error"
    assert result.output_truncated


def test_hidden_grader_injected_only_after(tmp_path: Path) -> None:
    task, run = _task(tmp_path, "import json\n" + OK_LINE + "\n")
    ws = e2e.prepare_workspace(task, run)
    assert not (ws / e2e.GRADER_DIRNAME).exists()
    (ws / "README.txt").unlink()
    result = e2e.run_grader(task, ws, run / "harness")
    assert (ws / e2e.GRADER_DIRNAME).exists()
    assert result.missing_files == ["README.txt"]
    assert result.status == "ok"
    assert result.full_pass
