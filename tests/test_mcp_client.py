from __future__ import annotations

import hashlib
import json
import time

import pytest

from cora.core.toolgroups import group_of
from cora.core.tools import ToolRegistry
from cora.core.tools.base import ToolResult
from cora.core.tools.mcp import build_tools, exposed_name
from mcp_util import alive, events, make_manager, server_cfg, starts

FAKE_ECHO_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def test_handshake_pagination_and_text(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        tools = mgr.ensure_tools(["fake"])
        assert len(tools) == 12
        lists = [
            e
            for e in events(log)
            if e.get("event") == "request" and e.get("method") == "tools/list"
        ]
        assert len(lists) == 2
        assert lists[1]["cursor"] == "page2"
        assert mgr.call_tool("fake", "echo", {"text": "hi"}) == ToolResult(True, "hi")
        mixed = mgr.call_tool("fake", "mixed", {})
        assert mixed.output == "before\n[non-text content omitted: image]\nafter"
        replies = [e["msg"] for e in events(log) if e.get("event") == "client_reply"]
        assert any("error" in m and m["error"]["code"] == -32601 for m in replies)
    finally:
        mgr.close()


def test_is_error_and_rpc_error(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        mgr.ensure_tools(["fake"])
        r = mgr.call_tool("fake", "fail", {})
        assert r.ok is False and "something went wrong" in r.output
        r = mgr.call_tool("fake", "rpc_error", {})
        assert r.ok is False and "-32602" in r.output
        r = mgr.call_tool("fake", "echo", {"text": "again"})
        assert r.ok is True
    finally:
        mgr.close()


def test_naming_rules(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    assert exposed_name("srv", "weird.name/x") == "mcp__srv__weird_name_x"
    name = exposed_name("srv", "t" * 100)
    assert len(name) == 64
    assert name.endswith("_" + hashlib.sha1(("t" * 100).encode()).hexdigest()[:8])
    assert exposed_name("srv", "t" * 100) == name
    tools, notes = build_tools(None, "srv", [{"name": "a.b"}, {"name": "a_b"}, {"name": 3}])
    assert [t.name for t in tools] == ["mcp__srv__a_b"]
    assert tools[0].tool == "a.b"
    assert len(notes) == 2
    assert group_of("mcp__srv__a_b") == "mcp:srv"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        by_tool = {t.tool: t for t in mgr.ensure_tools(["fake"])}
        assert by_tool["echo"].parameters == FAKE_ECHO_SCHEMA
        reg = ToolRegistry([by_tool["echo"]])
        assert reg.schemas()[0]["function"]["description"] == "Echo the text argument."
        assert by_tool["weird.name/x"].name == "mcp__fake__weird_name_x"
        assert by_tool["weird.name/x"].parameters == {"type": "object", "properties": {}}
    finally:
        mgr.close()


@pytest.mark.slow
def test_timeout(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log, timeout_s=0.5), close_grace_s=0.3)
    try:
        mgr.ensure_tools(["fake"])
        t0 = time.monotonic()
        r = mgr.call_tool("fake", "slow", {"seconds": 5})
        elapsed = time.monotonic() - t0
        assert r.ok is False and "timed out" in r.output
        assert 0.4 <= elapsed <= 2.0
        pids = starts(log)
    finally:
        mgr.close()
    assert pids and not any(alive(p) for p in pids)


def test_output_truncated(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        mgr.ensure_tools(["fake"])
        r = mgr.call_tool("fake", "big", {"n": 50000})
        assert r.ok is True
        assert len(r.output) <= 16000 + len("\n...[truncated: 34000 more chars]")
        assert "[truncated" in r.output
    finally:
        mgr.close()


@pytest.mark.slow
def test_oversize_message(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(
        tmp_path, server_cfg("fake", log), max_message_bytes=65536, close_grace_s=0.3
    )
    try:
        mgr.ensure_tools(["fake"])
        r = mgr.call_tool("fake", "hugeline", {"n": 200000})
        assert r.ok is False and "larger than 65536 bytes" in r.output
        assert mgr.statuses()[0].state == "crashed"
    finally:
        mgr.close()


def test_env_allowlist_and_secrets(tmp_path, monkeypatch, no_network):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    monkeypatch.setenv("SOME_PARENT_VAR", "x")
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log, env={"MY_TOKEN": "tok-12345"}))
    try:
        mgr.ensure_tools(["fake"])
        r = mgr.call_tool("fake", "env", {})
        env = json.loads(r.output)
    finally:
        mgr.close()
    assert "OPENROUTER_API_KEY" not in env
    assert "SOME_PARENT_VAR" not in env
    assert env["MY_TOKEN"] == "tok-12345"
    assert env["LANG"] == "C.UTF-8"
    assert env["LC_CTYPE"] == "C.UTF-8"
    assert "PATH" in env


def test_no_shell(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    extra = [f"; touch {p1}", f"$(touch {p2})", "a|b && c"]
    mgr = make_manager(tmp_path, server_cfg("fake", log, *extra))
    try:
        mgr.ensure_tools(["fake"])
        argv = events(log)[0]["argv"]
        for item in extra:
            assert item in argv
    finally:
        mgr.close()
    assert not p1.exists()
    assert not p2.exists()


def test_env_value_redacted_in_errors(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = server_cfg(
        "srv", log, "--env-var", "MY_TOKEN", mode="stderr_env", env={"MY_TOKEN": "tok-12345"}
    )
    mgr = make_manager(tmp_path, cfg)
    try:
        assert mgr.ensure_tools(["srv"]) == []
        last_error = mgr.statuses()[0].last_error or ""
        assert "[REDACTED]" in last_error
        assert "tok-12345" not in last_error
    finally:
        mgr.close()


@pytest.mark.slow
def test_close_kills_all_and_stubborn(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    normal = server_cfg("normal_srv", log)
    stubborn = server_cfg("stubborn", log, mode="ignore_stdin")
    mgr = make_manager(tmp_path, normal, stubborn, close_grace_s=0.3)
    mgr.ensure_tools(["normal_srv", "stubborn"])
    pids = starts(log)
    assert len(pids) == 2
    assert all(alive(p) for p in pids)
    mgr.close()
    assert not any(alive(p) for p in pids)


def test_crash_restart_then_failed(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log), close_grace_s=0.3)
    try:
        mgr.ensure_tools(["fake"])
        r1 = mgr.call_tool("fake", "crash", {})
        assert r1.ok is False and "crashed" in r1.output
        assert mgr.statuses()[0].state == "crashed"
        r2 = mgr.call_tool("fake", "crash", {})
        assert r2.ok is False and "crashed" in r2.output
        assert mgr.statuses()[0].state == "failed"
        r3 = mgr.call_tool("fake", "echo", {"text": "x"})
        assert r3.ok is False and "not restarted" in r3.output
        assert len(starts(log)) == 2
    finally:
        mgr.close()


def test_crash_then_recover(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log), close_grace_s=0.3)
    try:
        mgr.ensure_tools(["fake"])
        assert mgr.call_tool("fake", "crash", {}).ok is False
        assert mgr.call_tool("fake", "echo", {"text": "x"}).ok is True
        st = mgr.statuses()[0]
        assert st.restarts == 1
        assert st.state == "running"
    finally:
        mgr.close()


def test_badjson_marks_crashed(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log), close_grace_s=0.3)
    try:
        mgr.ensure_tools(["fake"])
        r = mgr.call_tool("fake", "badjson", {})
        assert r.ok is False and "invalid JSON" in r.output
        assert mgr.statuses()[0].state == "crashed"
    finally:
        mgr.close()


def test_crash_on_start_bounded(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log, mode="crash_on_start"), close_grace_s=0.3)
    try:
        states = []
        for _ in range(3):
            assert mgr.ensure_tools(["fake"]) == []
            states.append(mgr.statuses()[0].state)
        assert states == ["crashed", "failed", "failed"]
        assert len(starts(log)) == 2
        assert "boom" in (mgr.statuses()[0].last_error or "")
    finally:
        mgr.close()


def test_badjson_on_start(tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(
        tmp_path, server_cfg("fake", log, mode="badjson_on_start"), close_grace_s=0.3
    )
    try:
        assert mgr.ensure_tools(["fake"]) == []
        st = mgr.statuses()[0]
        assert st.state == "crashed"
        assert "invalid JSON" in (st.last_error or "")
    finally:
        mgr.close()
