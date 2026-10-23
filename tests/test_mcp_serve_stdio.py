from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from conftest import act
from mcp_serve_util import DEADLINE, FAKE_CFG, Proc, assert_frame, payload

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX"),
]


def _cfg(tmp_path: Path, text: str = FAKE_CFG) -> Path:
    path = tmp_path / "fake.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _script(tmp_path: Path, replies: list[str]) -> str:
    path = tmp_path / "script.json"
    path.write_text(json.dumps(replies), encoding="utf-8")
    return str(path)


def test_stdio_session_clean(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    env = {
        "CORA_FAKE_STRAY": "1",
        "CORA_FAKE_SCRIPT": _script(tmp_path, [act("list_files", {}), "Final Answer: done"]),
    }
    with Proc(_cfg(tmp_path), ws, tmp_path, env) as proc:
        proc.initialize()
        rid = proc.request("ping")
        assert proc.wait_response(rid)["result"] == {}
        rid = proc.request("tools/list")
        assert proc.wait_response(rid)["result"]["tools"]
        proc.send_raw(b"{bad\n")
        assert proc.recv()["error"]["code"] == -32700
        rid = proc.request("foo/bar")
        assert proc.wait_response(rid)["error"]["code"] == -32601
        proc.send({"jsonrpc": "2.0", "method": "notifications/whatever"})
        assert proc.call("nope", {})["error"]["code"] == -32602
        resp = proc.call("run_task", {"task": "q"}, rid="run-1")
        d = payload(resp)
        assert d["ok"] is True
        assert d["stop_reason"] == "final_answer"
        assert proc.close() == 0
    for line in proc.raw:
        assert_frame(line)
    assert "STRAY-PRINT" in proc.stderr_text()
    assert b"STRAY-PRINT" not in b"".join(proc.raw)


def test_stdio_eof_during_run(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    ready = tmp_path / "ready"
    env = {
        "CORA_FAKE_DELAY": "0.5",
        "CORA_FAKE_READY": str(ready),
        "CORA_FAKE_DEFAULT": act("list_files", {}),
    }
    with Proc(_cfg(tmp_path), ws, tmp_path, env) as proc:
        proc.initialize()
        proc.request("tools/call", {"name": "run_task", "arguments": {"task": "long"}}, rid=5)
        deadline = time.monotonic() + DEADLINE
        while not ready.exists():
            assert proc.proc.poll() is None, "server exited before the run started"
            assert time.monotonic() < deadline, "run never became ready"
            time.sleep(0.05)
        assert proc.close(timeout=10) == 0
    sessions = list((ws / ".cora" / "sessions").glob("*/session.json"))
    assert len(sessions) == 1
    assert json.loads(sessions[0].read_text("utf-8"))["stop_reason"] == "interrupted"
    for line in proc.raw:
        assert json.loads(line).get("id") != 5


def test_stdio_bad_config_exit_2(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = _cfg(tmp_path, FAKE_CFG + '\n[mcp]\napproval = "auto"\n')
    with Proc(cfg, ws, tmp_path) as proc:
        assert proc.proc.wait(timeout=10) == 2
        assert proc.close() == 2
    assert "invalid [mcp].approval" in proc.stderr_text()
    assert proc.raw == []
