from __future__ import annotations

import asyncio
import dataclasses
import json
import re

from conftest import native, tc, with_agent
from cora.core.agent import Agent
from cora.core.config import MemorySettings
from cora.core.delegation import DelegateTool
from cora.core.memory import WorkingMemory
from cora.core.native import NATIVE_EMPTY_REPLY, flatten_tool_messages
from cora.core.state import SessionStore, StopReason
from cora.core.tools import (
    ApprovalPolicy,
    ToolContext,
    ToolRegistry,
    ToolResult,
    Workspace,
    default_tools,
)
from cora.core.tools.builtin import RunShellTool
from cora.core.types import CompletionResponse, Message, NativeToolCall


async def _dummy_delegate(task: str) -> ToolResult:
    return ToolResult(True, "")


def _final(text: str) -> CompletionResponse:
    return CompletionResponse(text, 10, 5, "mock/cheap")


def _run(config, workspace, approval="auto", task="hi", **kw):
    agent = Agent(config, workspace, ApprovalPolicy(approval), **kw)
    return asyncio.run(agent.run(task))


def test_all_tool_schemas_valid():
    reg = ToolRegistry([*default_tools(), DelegateTool(_dummy_delegate)])
    schemas = reg.schemas()
    for s in schemas:
        assert s["type"] == "function"
        fn = s["function"]
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", fn["name"])
        assert fn["parameters"]["type"] == "object"
        assert set(fn["parameters"].get("required", [])) <= set(fn["parameters"]["properties"])
        json.dumps(s)
    assert {s["function"]["name"] for s in schemas} == set(reg.names())


def test_native_single_call(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [native(tc("read_file", {"path": "a.txt"})), _final("done")]
    r = _run(cfg, tmp_path)
    assert r.answer == "done"
    assert scripted.calls[0].tools is not None
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert scripted.calls[1].messages[-2].tool_calls
    last = scripted.calls[1].messages[-1]
    assert last.role == "tool"
    assert last.tool_call_id == "c1"
    assert "hello" in last.content


def test_native_multi_readonly_uses_execute_many(mock_config, scripted, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    seen: list[list] = []
    original = ToolRegistry.execute_many

    async def spy(self, calls, ctx, max_concurrency):
        seen.append(list(calls))
        return await original(self, calls, ctx, max_concurrency)

    monkeypatch.setattr(ToolRegistry, "execute_many", spy)
    scripted.script[:] = [
        native(tc("read_file", {"path": "a.txt"}, "c1"), tc("read_file", {"path": "b.txt"}, "c2")),
        _final("both read"),
    ]
    r = _run(cfg, tmp_path)
    assert r.answer == "both read"
    assert len(seen) == 1
    assert len(seen[0]) == 2
    tail = scripted.calls[1].messages[-2:]
    assert [m.role for m in tail] == ["tool", "tool"]
    assert [m.tool_call_id for m in tail] == ["c1", "c2"]


def test_native_text_only_is_final(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [_final("just text")]
    r = _run(cfg, tmp_path)
    assert r.answer == "just text"
    assert len(scripted.calls) == 1


def test_native_invalid_json_args_retries(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [native(tc("read_file", "{bad", "c1")), _final("final")]
    r = _run(cfg, tmp_path)
    tool_msgs = [m for m in scripted.calls[1].messages if m.role == "tool"]
    assert tool_msgs[0].content.startswith("error: invalid JSON arguments")
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_native_unknown_tool(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [native(tc("nope", {})), _final("final")]
    _run(cfg, tmp_path)
    tool_msgs = [m for m in scripted.calls[1].messages if m.role == "tool"]
    assert "unknown tool 'nope'" in tool_msgs[0].content


def test_native_empty_reply_then_final(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [_final(""), _final("final")]
    _run(cfg, tmp_path)
    assert any(
        m.role == "user" and m.content == NATIVE_EMPTY_REPLY for m in scripted.calls[1].messages
    )


def test_native_iteration_limit(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, tool_protocol="native", max_iterations=2)
    scripted.script[:] = [native(tc("list_files", {}, f"c{i}")) for i in range(5)]
    r = _run(cfg, tmp_path)
    assert r.stop_reason == StopReason.MAX_ITERATIONS
    assert len(scripted.calls) == 2


def test_native_permission_denied(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [
        native(tc("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"})),
        _final("gave up"),
    ]
    _run(cfg, tmp_path, approval="deny")
    tool_msgs = [m for m in scripted.calls[1].messages if m.role == "tool"]
    assert "denied by user" in tool_msgs[0].content
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"


def test_native_session_persists_tool_messages(mock_config, scripted, tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    cfg = with_agent(mock_config, tool_protocol="native")
    scripted.script[:] = [native(tc("read_file", {"path": "a.txt"})), _final("done")]
    r = _run(cfg, tmp_path)
    sid = r.session.id
    mem = SessionStore(tmp_path / ".cora" / "sessions").load(sid).memory
    tool_entries = [d for d in mem["recent"] if d.get("role") == "tool"]
    assert tool_entries
    assert "tool_call_id" in tool_entries[0]
    rebuilt = WorkingMemory.from_dict(mem, cfg.memory, None, sid).to_dict()
    assert rebuilt == mem


def test_memory_never_starts_with_orphan_tool():
    calls = (NativeToolCall("c1", "read_file", "{}"), NativeToolCall("c2", "read_file", "{}"))
    recent = [
        Message("user", "u"),
        Message("assistant", "", tool_calls=calls),
        Message("tool", "a", tool_call_id="c1"),
        Message("tool", "b", tool_call_id="c2"),
        Message("assistant", "x"),
    ]
    mem = WorkingMemory(MemorySettings())
    mem.recent = list(recent)
    assert mem.compact(keep=2) == 2
    assert mem.recent == [Message("assistant", "x")]

    small = WorkingMemory(
        dataclasses.replace(MemorySettings(), context_budget_tokens=60, keep_last_messages=1)
    )
    small.recent = list(recent)
    small.build("sys")
    assert not small.recent or small.recent[0].role != "tool"


def test_react_mode_request_shape(mock_config, scripted, tmp_path):
    scripted.script[:] = ["Thought: done\nFinal Answer: ok"]
    _run(mock_config, tmp_path)
    assert scripted.calls[0].tools is None
    assert scripted.calls[0].stop == ["\nObservation:"]


def test_flatten_tool_messages():
    msgs = [
        Message("assistant", "", tool_calls=(tc("list_files", {}),)),
        Message("tool", "out", tool_call_id="c1"),
    ]
    flat = flatten_tool_messages(msgs)
    assert flat[0] == Message("assistant", "Action: list_files\nAction Input: {}")
    assert flat[1].role == "user"
    assert flat[1].content == "Observation: out"


def test_native_streaming_agent(mock_config, scripted, tmp_path):
    cfg = dataclasses.replace(
        with_agent(mock_config, tool_protocol="native"),
        models=tuple(
            dataclasses.replace(m, provider="scripted_stream") for m in mock_config.models
        ),
    )
    scripted.script[:] = [native(tc("list_files", {})), _final("streamed answer")]
    deltas: list[str] = []
    r = _run(cfg, tmp_path, on_answer_delta=deltas.append)
    assert "".join(deltas) == "streamed answer"
    assert r.answer == "streamed answer"


def test_run_shell_hides_api_key_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-DUMMY-not-a-real-key-000")
    ctx = ToolContext(
        Workspace(tmp_path),
        ApprovalPolicy("auto"),
        10,
        hidden_env=frozenset({"OPENROUTER_API_KEY"}),
    )
    res = asyncio.run(RunShellTool().run({"command": "env"}, ctx))
    assert "DUMMY" not in res.output
