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
from cora.core.outcome import OUTCOME_KEYS

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals"),
]

ENTRY = Path(__file__).with_name("headless_entry.py")
DEADLINE = 30
CFG = CFG_TOML.replace('provider = "scripted"', 'provider = "headless_fake"')


def _spawn(tmp_path: Path, args: list[str], extra_env: dict[str, str]):
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "CORA_TUI")}
    env["HOME"] = str(tmp_path / "home")
    env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, str(ENTRY), "run", *args, "-w", str(ws), "-c", str(cfg)],
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


def _finish(proc: subprocess.Popen) -> tuple[bytes, bytes]:
    try:
        return proc.communicate(timeout=DEADLINE)
    except subprocess.TimeoutExpired:
        _kill(proc)
        pytest.fail("process did not exit within 30 s")


def test_subprocess_json_one_document(tmp_path):
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps([act("list_files", {}), act("list_files", {}), "Final Answer: ok"]),
        encoding="utf-8",
    )
    proc, _ = _spawn(
        tmp_path,
        ["x", "--headless", "--json"],
        {"CORA_FAKE_STRAY": "1", "CORA_FAKE_SCRIPT": str(script)},
    )
    try:
        out, err = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == 0
    assert out.decode().count("\n") == 1
    d = json.loads(out)
    assert set(d) == set(OUTCOME_KEYS)
    assert b"STRAY-PRINT" in err
    assert d["exit_code"] == 0


@pytest.mark.parametrize(
    "sig,code",
    [(signal.SIGTERM, 143), (signal.SIGINT, 130)],
    ids=["sigterm", "sigint"],
)
def test_signal_interrupts(tmp_path, sig, code):
    ready = tmp_path / "ready"
    env = {
        "CORA_FAKE_DEFAULT": act("list_files", {}),
        "CORA_FAKE_DELAY": "0.5",
        "CORA_FAKE_READY": str(ready),
    }
    proc, ws = _spawn(tmp_path, ["loop", "--headless", "--json", "--max-iterations", "200"], env)
    try:
        _wait_ready(proc, ready)
        proc.send_signal(sig)
        out, _ = _finish(proc)
    finally:
        _kill(proc)
    assert proc.returncode == code
    assert out.decode().count("\n") == 1
    d = json.loads(out)
    assert set(d) == set(OUTCOME_KEYS)
    assert d["stop_reason"] == "interrupted"
    assert d["exit_code"] == code
    stored = json.loads(
        (ws / ".cora" / "sessions" / d["session_id"] / "session.json").read_text(encoding="utf-8")
    )
    assert stored["stop_reason"] == "interrupted"
