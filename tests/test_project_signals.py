from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import CFG_TOML, act
from cora.core.milestones import PROJECT_KEYS

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals"),
]

ENTRY = Path(__file__).with_name("headless_entry.py")
DEADLINE = 30
CFG = CFG_TOML.replace('provider = "scripted"', 'provider = "headless_fake"')
THREE_TOML = """goal = "ship"

[[milestones]]
id = "m1"
title = "one"
task = "alpha-task"

[[milestones]]
id = "m2"
title = "two"
task = "beta-task"

[[milestones]]
id = "m3"
title = "three"
task = "gamma-task"
"""


def _spawn_project(tmp_path: Path, args: list[str], extra_env: dict[str, str]):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG, encoding="utf-8")
    (tmp_path / "plan.toml").write_text(THREE_TOML, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "CORA_TUI")}
    env["HOME"] = str(tmp_path / "home")
    env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(ENTRY), "project", *args, "-w", str(ws), "-c", str(cfg)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=tmp_path,
        start_new_session=True,
    )
    return proc, ws


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.communicate()


def _finish(proc: subprocess.Popen) -> tuple[bytes, bytes]:
    try:
        return proc.communicate(timeout=DEADLINE)
    except subprocess.TimeoutExpired:
        _kill(proc)
        pytest.fail("process did not exit within 30 s")


def _wait_ready(proc: subprocess.Popen, ready: Path) -> None:
    deadline = time.monotonic() + DEADLINE
    while not ready.exists():
        if proc.poll() is not None:
            _, err = proc.communicate()
            pytest.fail(f"process exited before ready: {err.decode(errors='replace')}")
        if time.monotonic() > deadline:
            _kill(proc)
            pytest.fail("process never became ready")
        time.sleep(0.05)


def _wait_current(proc: subprocess.Popen, ws: Path, mid: str) -> Path:
    deadline = time.monotonic() + DEADLINE
    while True:
        for path in (ws / ".cora" / "projects").glob("*/checkpoint.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("current") == mid:
                return path
        if proc.poll() is not None:
            _, err = proc.communicate()
            pytest.fail(f"process exited before {mid} started: {err.decode(errors='replace')}")
        if time.monotonic() > deadline:
            _kill(proc)
            pytest.fail(f"milestone {mid} never became current")
        time.sleep(0.05)


def _only_checkpoint(ws: Path) -> Path:
    paths = list((ws / ".cora" / "projects").glob("*/checkpoint.json"))
    assert len(paths) == 1
    return paths[0]


def _one_line(out: bytes) -> dict:
    text = out.decode()
    assert text.endswith("\n")
    assert text.count("\n") == 1
    return json.loads(text)


def test_subprocess_three_completed(tmp_path):
    proc, _ = _spawn_project(
        tmp_path, ["run", str(tmp_path / "plan.toml"), "--headless", "--json"], {}
    )
    try:
        out, _ = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == 0
    d = _one_line(out)
    assert set(d) == set(PROJECT_KEYS)
    assert [m["status"] for m in d["milestones"]] == ["completed"] * 3
    assert len({m["session_id"] for m in d["milestones"]}) == 3
    cp = json.loads(
        (tmp_path / "ws" / ".cora" / "projects" / d["run_id"] / "checkpoint.json").read_text(
            encoding="utf-8")
    )
    assert cp["completed"] == ["m1", "m2", "m3"]


def test_sigkill_then_resume(tmp_path):
    log1 = tmp_path / "log1.jsonl"
    log2 = tmp_path / "log2.jsonl"
    proc, ws = _spawn_project(
        tmp_path,
        ["run", str(tmp_path / "plan.toml"), "--headless", "--json"],
        {"CORA_FAKE_DELAY": "1.0", "CORA_FAKE_LOG": str(log1)},
    )
    try:
        path = _wait_current(proc, ws, "m2")
        proc.kill()
        proc.communicate()
    finally:
        _kill(proc)
    cp = json.loads(path.read_text(encoding="utf-8"))
    assert cp["completed"] == ["m1"]
    assert cp["current"] == "m2"
    assert cp["milestones"]["m2"]["status"] != "completed"
    run_id = cp["run_id"]

    proc, _ = _spawn_project(
        tmp_path,
        ["resume", run_id, "--headless", "--json"],
        {"CORA_FAKE_LOG": str(log2)},
    )
    try:
        out, _ = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == 0
    d = _one_line(out)
    assert [m["status"] for m in d["milestones"]] == ["completed"] * 3

    lines1 = [json.loads(ln)["task"] for ln in log1.read_text(encoding="utf-8").splitlines()]
    lines2 = [json.loads(ln)["task"] for ln in log2.read_text(encoding="utf-8").splitlines()]
    assert sum("alpha-task" in t for t in lines1) == 1
    assert not any("alpha-task" in t for t in lines2)
    assert any("beta-task" in t for t in lines2)
    assert any("gamma-task" in t for t in lines2)


@pytest.mark.parametrize(
    "sig,code",
    [(signal.SIGTERM, 143), (signal.SIGINT, 130)],
    ids=["sigterm", "sigint"],
)
def test_signal_then_resume(tmp_path, sig, code):
    ready = tmp_path / "ready"
    env = {
        "CORA_FAKE_DEFAULT": act("list_files", {}),
        "CORA_FAKE_DELAY": "0.5",
        "CORA_FAKE_READY": str(ready),
    }
    proc, ws = _spawn_project(
        tmp_path,
        ["run", str(tmp_path / "plan.toml"), "--headless", "--json", "--max-iterations", "200"],
        env,
    )
    try:
        _wait_ready(proc, ready)
        proc.send_signal(sig)
        out, _ = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == code
    d = _one_line(out)
    assert set(d) == set(PROJECT_KEYS)
    assert d["stop_reason"] == "interrupted"
    assert d["exit_code"] == code
    assert [m["status"] for m in d["milestones"]] == ["interrupted", "pending", "pending"]
    cp = json.loads(_only_checkpoint(ws).read_text(encoding="utf-8"))
    assert cp["completed"] == []

    proc, _ = _spawn_project(
        tmp_path,
        ["resume", d["run_id"], "--headless", "--json", "--max-iterations", "200"],
        {"CORA_FAKE_DEFAULT": "Final Answer: done"},
    )
    try:
        out, _ = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == 0
    d = _one_line(out)
    assert [m["status"] for m in d["milestones"]] == ["completed"] * 3
