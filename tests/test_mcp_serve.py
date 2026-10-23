from __future__ import annotations

import io
import itertools
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from conftest import CFG_TOML, FIXED_CFG_TOML, act
from cora import __version__
from cora.cli import mcp_serve
from cora.core.agent import RunResult
from cora.core.observability import read_events
from cora.core.outcome import outcome_dict
from cora.core.state import Session, SessionStore, StopReason
from mcp_serve_util import (
    DEADLINE,
    InProc,
    assert_frame,
    payload,
    serve_cfg,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _slow(req) -> str:
    time.sleep(0.4)
    return act("list_files", {})


@pytest.fixture(autouse=True)
def depth_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORA_MCP_DEPTH", "0")


def _session_json(ws: Path, sid: str) -> dict:
    return json.loads((ws / ".cora" / "sessions" / sid / "session.json").read_text("utf-8"))


def test_initialize_ping_tools_list(ws, tmp_path):
    with InProc(serve_cfg(tmp_path), ws) as srv:
        resp = srv.initialize()
        result = resp["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"] == {"name": "cora", "version": __version__}
        rid = srv.request("initialize", {"protocolVersion": "1999-01-01"})
        assert srv.wait_response(rid)["result"]["protocolVersion"] == "2025-06-18"
        srv.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        ping_rid = srv.request("ping")
        ping = srv.recv()
        assert ping["id"] == ping_rid
        assert ping["result"] == {}
        list_rid = srv.request("tools/list")
        tools = srv.wait_response(list_rid)["result"]["tools"]
        assert {t["name"] for t in tools} == {"run_task", "resume_session", "list_sessions"}
        assert all(t["inputSchema"]["type"] == "object" for t in tools)
        assert srv.close() == 0


def test_run_task_result(scripted, ws, tmp_path, no_network):
    scripted.script.append("Final Answer: hello")
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        d = srv.doc(srv.call("run_task", {"task": "q"}))
        assert d["ok"] is True
        assert d["stop_reason"] == "final_answer"
        assert d["final_answer"] == "hello"
        assert isinstance(d["cost_usd"], float)
        assert d["truncated"] is False
        assert d["budget"]["limits"] == {
            "cost_usd": 0.5,
            "iterations": 30,
            "wall_s": 600.0,
            "tool_calls": 200,
        }
        assert d["policy"]["mode"] == "policy"
        assert srv.close() == 0


def test_protocol_errors(scripted, ws, tmp_path):
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        srv.send_raw(b"{not json\n")
        err = srv.recv()
        assert err["error"]["code"] == -32700
        assert err["id"] is None
        rid = srv.request("ping")
        assert srv.wait_response(rid)["result"] == {}
        rid = srv.request("foo/bar")
        assert srv.wait_response(rid)["error"]["code"] == -32601
        srv.send({"jsonrpc": "2.0", "method": "notifications/whatever"})
        rid = srv.request("ping")
        assert srv.recv()["id"] == rid
        srv.send_raw(b"[]\n")
        bad = srv.recv()
        assert bad["error"]["code"] == -32600
        assert bad["id"] is None
        assert srv.call("nope", {})["error"]["code"] == -32602
        assert srv.call("run_task", {})["error"]["code"] == -32602
        assert srv.call("run_task", {"task": "x", "extra": 1})["error"]["code"] == -32602
        assert scripted.calls == []
        assert srv.close() == 0
    for line in srv.raw:
        assert_frame(line)


def test_eof_exits_zero(ws, tmp_path):
    srv = InProc(serve_cfg(tmp_path), ws)
    init_rid = srv.initialize()["id"]
    ping_rid = srv.request("ping")
    assert srv.recv()["id"] == ping_rid
    assert srv.close() == 0
    assert [assert_frame(x)["id"] for x in srv.raw] == [init_rid, ping_rid]


@pytest.mark.parametrize("raw", ["1", "abc", "-1"])
def test_depth_guard(scripted, ws, tmp_path, monkeypatch, raw):
    monkeypatch.setenv("CORA_MCP_DEPTH", raw)
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        for resp in (
            srv.call("run_task", {"task": "q"}),
            srv.call("resume_session", {"session_id": "20990101-000000-abcdef"}),
        ):
            d = srv.doc(resp)
            assert resp["result"]["isError"] is True
            assert d["stop_reason"] == "depth_exceeded"
            assert d["cost_usd"] == 0.0
            assert "CORA_MCP_DEPTH" in d["errors"][0]
            assert raw in d["errors"][0]
            assert "max_depth=1" in d["errors"][0]
        listed = srv.call("list_sessions", {})
        assert listed["result"]["isError"] is False
        assert scripted.calls == []
        assert srv.close() == 0
    assert os.environ["CORA_MCP_DEPTH"] == raw


@pytest.mark.parametrize(
    ("env_value", "mcp", "seen"),
    [("0", "", "1"), (None, "", "1"), ("1", "max_depth = 2", "2")],
)
def test_depth_ok_and_child_sees_increment(
    scripted, ws, tmp_path, monkeypatch, env_value, mcp, seen
):
    if shutil.which("python") is None:
        pytest.skip("python not on PATH")
    if env_value is None:
        monkeypatch.delenv("CORA_MCP_DEPTH")
    else:
        monkeypatch.setenv("CORA_MCP_DEPTH", env_value)
    (ws / "show_depth.py").write_text(
        'import os\nprint("depth=" + os.environ.get("CORA_MCP_DEPTH", "unset"))\n',
        encoding="utf-8",
    )
    scripted.script.extend(
        [act("run_shell", {"command": "python show_depth.py"}), "Final Answer: ok"]
    )
    with InProc(serve_cfg(tmp_path, mcp=mcp), ws) as srv:
        srv.initialize()
        d = srv.doc(srv.call("run_task", {"task": "q"}))
        assert d["ok"] is True
        assert f"depth={seen}" in str(scripted.calls[-1].messages)
        assert srv.close() == 0


def test_budget_clamped(scripted, ws, tmp_path, no_network):
    mcp = "max_cost_usd = 0.4\nmax_iterations = 3\nmax_wall_s = 250\nmax_tool_calls = 2"
    with InProc(serve_cfg(tmp_path, mcp=mcp), ws) as srv:
        srv.initialize()
        scripted.script.append("Final Answer: x")
        d = srv.doc(
            srv.call(
                "run_task",
                {"task": "q", "max_cost_usd": 0, "max_iterations": 100, "max_wall_s": 0,
                 "max_tool_calls": 1000},
            )
        )
        assert d["budget"]["limits"] == {
            "cost_usd": 0.4,
            "iterations": 3,
            "wall_s": 250.0,
            "tool_calls": 2,
        }
        scripted.script.append("Final Answer: y")
        d = srv.doc(srv.call("run_task", {"task": "q", "max_iterations": 2}))
        assert d["budget"]["limits"] == {
            "cost_usd": 0.4,
            "iterations": 2,
            "wall_s": 250.0,
            "tool_calls": 2,
        }
        assert srv.close() == 0


CAP_CASES = [
    ("iterations", "max_iterations = 3", CFG_TOML, [act("list_files", {})] * 10, None, 3),
    ("tool_calls", "max_tool_calls = 2", CFG_TOML, [act("list_files", {})] * 10, None, 3),
    ("cost", "max_cost_usd = 0.005", FIXED_CFG_TOML, [act("list_files", {})] * 20, None, None),
    ("wall", "max_wall_s = 250", CFG_TOML, [act("list_files", {})] * 10, "clock", None),
]


@pytest.mark.parametrize(("cap", "mcp", "base", "actions", "clock", "calls"), CAP_CASES)
def test_budget_caps_trip(
    scripted, ws, tmp_path, no_network, monkeypatch, cap, mcp, base, actions, clock, calls
):
    if clock:
        monkeypatch.setattr(mcp_serve, "_clock", itertools.count(0, 100).__next__)
    scripted.script.extend(actions + ["Final Answer: never"])
    with InProc(serve_cfg(tmp_path, mcp=mcp, base=base), ws) as srv:
        srv.initialize()
        resp = srv.call("run_task", {"task": "q"})
        d = srv.doc(resp)
        assert resp["result"]["isError"] is True
        assert d["stop_reason"] == "budget_exceeded"
        assert d["budget"]["tripped"] == cap
        assert (ws / ".cora" / "sessions" / d["session_id"] / "session.json").exists()
        if cap == "wall":
            assert len(scripted.calls) <= 2
        elif calls is not None:
            assert len(scripted.calls) == calls
        if cap == "tool_calls":
            assert d["budget"]["used"]["tool_calls"] == 2
        if cap == "cost":
            assert d["budget"]["used"]["cost_usd"] <= 0.005 + 0.0012 + 1e-9
        assert srv.close() == 0


@pytest.mark.parametrize(
    "args",
    [
        {"max_cost_usd": -1},
        {"max_iterations": "5"},
        {"max_iterations": 1.5},
        {"max_tool_calls": True},
        {"max_wall_s": -0.1},
    ],
)
def test_invalid_budget_args(scripted, ws, tmp_path, args):
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        resp = srv.call("run_task", {"task": "q", **args})
        assert resp["error"]["code"] == -32602
        assert scripted.calls == []
        assert srv.close() == 0


def test_invalid_limit_arg(scripted, ws, tmp_path):
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        assert srv.call("list_sessions", {"limit": 0})["error"]["code"] == -32602
        assert scripted.calls == []
        assert srv.close() == 0


@pytest.mark.parametrize(
    ("snippet", "key"),
    [
        ("max_cost_usd = 0", "max_cost_usd"),
        ("max_iterations = 0", "max_iterations"),
        ("max_wall_s = 0", "max_wall_s"),
        ("max_tool_calls = 0", "max_tool_calls"),
        ("max_output_chars = 999", "max_output_chars"),
        ('approval = "auto"', "approval"),
        ('approval = "ask"', "approval"),
    ],
)
def test_bad_config_exit_2(ws, tmp_path, capsys, snippet, key):
    cfg = serve_cfg(tmp_path, mcp=snippet)
    buf = io.BytesIO()
    code = mcp_serve.serve(cfg, ws, stdin=io.BytesIO(b""), stdout=buf)
    assert code == 2
    assert buf.getvalue() == b""
    assert f"invalid [mcp].{key}" in capsys.readouterr().err


def test_truncation(scripted, ws, tmp_path, no_network):
    scripted.script.append("Final Answer: " + "A" * 5000)
    with InProc(serve_cfg(tmp_path, mcp="max_output_chars = 1000"), ws) as srv:
        srv.initialize()
        resp = srv.call("run_task", {"task": "q"})
        text = resp["result"]["content"][0]["text"]
        assert len(text) <= 1000
        d = json.loads(text)
        assert d["truncated"] is True
        assert "[truncated:" in d["final_answer"]
        assert d["session_id"] in d["final_answer"]
        assert _session_json(ws, d["session_id"])["final_answer"].count("A") == 5000
        scripted.script.append("Final Answer: short")
        short = srv.doc(srv.call("run_task", {"task": "q"}))
        assert short["truncated"] is False
        assert srv.close() == 0


def _seed_sessions(ws: Path) -> None:
    store = SessionStore(ws / ".cora" / "sessions")
    for i in range(30):
        store.save(
            Session(
                id=f"20260101-0000{i:02d}-abcdef",
                task="t" * 2000,
                created_at=f"2026-01-01T00:00:{i:02d}+00:00",
            )
        )


def test_list_sessions_limit_and_cap(scripted, ws, tmp_path):
    _seed_sessions(ws)
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        resp = srv.call("list_sessions", {})
        d = payload(resp)
        assert resp["result"]["isError"] is False
        assert d["count"] == 20
        ids = [s["session_id"] for s in d["sessions"]]
        assert ids[0] == "20260101-000029-abcdef"
        assert ids == sorted(ids, reverse=True)
        assert all(len(s["task"]) <= 121 for s in d["sessions"])
        big = payload(srv.call("list_sessions", {"limit": 500}))
        assert big["count"] <= 100
        assert big["total"] == 30
        assert srv.close() == 0
    with InProc(serve_cfg(tmp_path, mcp="max_output_chars = 1000", name="small.toml"), ws) as srv:
        srv.initialize()
        resp = srv.call("list_sessions", {})
        text = resp["result"]["content"][0]["text"]
        assert len(text) <= 1000
        d = json.loads(text)
        assert d["truncated"] is True
        assert d["cost_usd"] == 0.0
        assert scripted.calls == []
        assert srv.close() == 0


def test_policy_safety(scripted, ws, tmp_path, no_network):
    (ws / ".env").write_text("TOKEN=topsecret-1", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core] topsecret-2", encoding="utf-8")
    before = {p: p.read_text("utf-8") for p in (ws / ".env", ws / ".git" / "config")}
    git = shutil.which("git")

    def repo_status() -> str:
        return subprocess.run(
            [git, "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout

    status_before = repo_status() if git else None
    scripted.script.extend([
        act("read_file", {"path": ".env"}),
        act("search", {"pattern": "topsecret", "path": ".env"}),
        act("list_files", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .env"}),
        act("read_file", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .git/config"}),
        "Final Answer: done",
    ])
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        d = srv.doc(srv.call("run_task", {"task": "q"}))
        assert srv.close() == 0
    assert d["policy"]["deny"] >= 5
    assert b"topsecret-" not in b"".join(srv.raw)
    for e in read_events(ws / ".cora" / "sessions" / d["session_id"] / "events.jsonl"):
        if e["type"] == "tool_call":
            assert "topsecret-" not in str(e.get("output_head", ""))
    assert {p: p.read_text("utf-8") for p in before} == before
    if git:
        assert repo_status() == status_before


def test_ask_resolves_deny(scripted, ws, tmp_path, no_network):
    scripted.script.extend([act("web_fetch", {"url": "https://example.com"}), "Final Answer: ok"])
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        d = srv.doc(srv.call("run_task", {"task": "q"}))
        assert srv.close() == 0
    assert d["policy"]["ask_resolved_deny"] == 1
    assert d["stop_reason"] == "final_answer"


def test_policy_blocked():
    r = RunResult(
        Session(id="20260101-000000-abcdef", task="q"),
        None,
        StopReason.TRIPWIRE,
        {"policy": {"deny": 1}},
        Path("events.jsonl"),
    )
    d = mcp_serve.fit_result(outcome_dict(r, None, wall_s=0.0), 20000)
    assert d["stop_reason"] == "policy_blocked"
    assert d["ok"] is False
    assert mcp_serve.tool_result(d)["isError"] is True


def test_resume_and_list(scripted, ws, tmp_path, no_network):
    with InProc(serve_cfg(tmp_path, base=FIXED_CFG_TOML), ws) as srv:
        srv.initialize()
        scripted.script.append("Final Answer: one")
        first = srv.doc(srv.call("run_task", {"task": "q1"}))
        scripted.script.append("Final Answer: two")
        second = srv.doc(srv.call("run_task", {"task": "q2"}))
        sid1, sid2 = first["session_id"], second["session_id"]
        c1 = first["cost_usd"]
        calls_before = len(scripted.calls)
        listed = srv.call("list_sessions", {})
        ld = payload(listed)
        assert [s["session_id"] for s in ld["sessions"][:2]] == [sid2, sid1]
        assert set(ld["sessions"][0]) >= {
            "session_id", "created_at", "task", "stop_reason", "cost_usd",
        }
        assert ld["cost_usd"] == 0.0
        assert len(scripted.calls) == calls_before
        scripted.script.extend([act("list_files", {})] * 5)
        resumed = srv.doc(
            srv.call(
                "resume_session",
                {"session_id": sid1, "task": "follow up", "max_cost_usd": c1 + 0.0005},
            )
        )
        assert resumed["budget"]["tripped"] == "cost"
        assert resumed["budget"]["used"]["cost_usd"] >= c1
        assert resumed["stop_reason"] == "budget_exceeded"
        unknown = srv.call("resume_session", {"session_id": "20990101-000000-ffffff"})
        assert unknown["result"]["isError"] is True
        msg = payload(unknown)["errors"][0]
        assert "unknown session id" in msg
        assert "20990101-000000-ffffff" in msg
        assert srv.call("resume_session", {"session_id": "../x"})["error"]["code"] == -32602
        assert srv.close() == 0


@pytest.mark.slow
def test_concurrency(scripted, ws, tmp_path, no_network):
    slow = _slow
    scripted.script.extend([slow] * 6 + ["Final Answer: done"])
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        srv.request(
            "tools/call",
            {"name": "run_task", "arguments": {"task": "long"}},
            rid=10,
        )
        deadline = time.monotonic() + 10
        while not scripted.calls:
            assert time.monotonic() < deadline, "run never started"
            time.sleep(0.05)
        for method, params in (("ping", None), ("tools/list", None),
                               ("tools/call", {"name": "list_sessions", "arguments": {}})):
            started = time.monotonic()
            srv.request(method, params, rid=f"q-{method}")
            assert srv.wait_response(f"q-{method}", timeout=2)
            assert time.monotonic() - started < 2
        busy = srv.doc(
            srv.call("run_task", {"task": "second"}, rid=11)
        )
        assert busy["stop_reason"] == "busy"
        assert busy["iterations"] == 0
        done = srv.doc(srv.wait_response(10))
        assert done["ok"] is True
        assert len(scripted.calls) == 7
        assert srv.close() == 0


@pytest.mark.slow
def test_cancel(scripted, ws, tmp_path, no_network):
    slow = _slow
    scripted.script.extend([slow] * 20 + ["Final Answer: never"])
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        srv.request(
            "tools/call",
            {"name": "run_task", "arguments": {"task": "long"}},
            rid="r1",
        )
        deadline = time.monotonic() + 10
        while not scripted.calls:
            assert time.monotonic() < deadline, "run never started"
            time.sleep(0.05)
        srv.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                  "params": {"requestId": "zzz"}})
        srv.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                  "params": {"requestId": "r1", "reason": "test"}})
        deadline = time.monotonic() + 10
        stopped = False
        while not stopped:
            assert time.monotonic() < deadline, "session never saved as interrupted"
            for path in (ws / ".cora" / "sessions").glob("*/session.json"):
                if json.loads(path.read_text("utf-8")).get("stop_reason") == "interrupted":
                    stopped = True
            time.sleep(0.05)
        rid = srv.request("ping")
        assert srv.wait_response(rid)["result"] == {}
        assert all(json.loads(line).get("id") != "r1" for line in srv.raw)
        assert len(scripted.calls) < 20
        scripted.script.clear()
        scripted.script.append("Final Answer: again")
        deadline = time.monotonic() + 10
        while True:
            resp = srv.call("run_task", {"task": "again"})
            if "result" in resp and resp["result"]["isError"] is False:
                break
            assert time.monotonic() < deadline, "run did not become available after cancel"
            time.sleep(0.05)
        assert payload(resp)["final_answer"] == "again"
        assert srv.close() == 0
    for line in srv.raw:
        assert_frame(line)


@pytest.mark.slow
def test_progress(scripted, ws, tmp_path, no_network):
    slow = _slow
    with InProc(serve_cfg(tmp_path), ws) as srv:
        srv.initialize()
        scripted.script.extend([slow] * 4 + ["Final Answer: done"])
        rid = srv.request(
            "tools/call",
            {"name": "run_task", "arguments": {"task": "p"}, "_meta": {"progressToken": "tok-1"}},
        )
        before, times = [], []
        while True:
            msg = srv.recv()
            if msg.get("id") == rid:
                break
            before.append(msg)
            times.append(time.monotonic())
        assert len(before) >= 2
        assert all(m["method"] == "notifications/progress" for m in before)
        assert all(m["params"]["progressToken"] == "tok-1" for m in before)
        progress = [m["params"]["progress"] for m in before]
        assert progress == sorted(set(progress))
        assert all(b - a >= 0.8 for a, b in zip(times, times[1:], strict=False))
        rid_ping = srv.request("ping")
        assert srv.recv()["id"] == rid_ping

        scripted.script.extend([slow] * 4 + ["Final Answer: done"])
        plain = srv.request(
            "tools/call", {"name": "run_task", "arguments": {"task": "p2"}}
        )
        seen = []
        while True:
            msg = srv.recv(timeout=DEADLINE)
            if msg.get("id") == plain:
                break
            seen.append(msg)
        assert seen == []
        assert srv.close() == 0
