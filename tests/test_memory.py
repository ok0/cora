from __future__ import annotations

import asyncio

from conftest import act
from cora.core.agent import Agent
from cora.core.config import MemorySettings, parse_config
from cora.core.memory import PersistentStore, WorkingMemory
from cora.core.observability import read_events
from cora.core.state import SessionStore
from cora.core.tools import ApprovalPolicy
from cora.core.types import Message, messages_tokens


def test_context_within_budget_over_60_tool_calls(scripted, mock_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "big.txt").write_text(
        "\n".join(f"line {i} " + "x" * 60 for i in range(5000)) + "\n",
        encoding="utf-8",
    )
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
                {
                    "id": "mock/strong",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto", "max_iterations": 80},
            "memory": {
                "context_budget_tokens": 6000,
                "keep_last_messages": 6,
                "max_observation_chars": 4000,
            },
        }
    )
    scripted.script[:] = [
        act("read_file", {"path": "big.txt", "start_line": 1 + 50 * i}) for i in range(60)
    ] + ["Final Answer: done"]
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run("read big file"))

    events = read_events(r.log_path)
    assert sum(1 for e in events if e["type"] == "tool_call") >= 50
    for req in scripted.calls:
        assert messages_tokens(req.messages) <= 6000
    assert any(
        m.content.startswith("Summary of earlier steps:")
        for req in scripted.calls[1:]
        for m in req.messages
    )
    evicted = PersistentStore(ws / ".cora" / "memory").read(r.session.id, "evicted")
    assert evicted


def test_working_memory_roundtrip():
    settings = MemorySettings()
    mem = WorkingMemory(settings)
    mem.pin(Message("user", "Task: x"))
    mem.add(Message("assistant", "a"))
    mem.summary_lines.append("- user: y")
    restored = WorkingMemory.from_dict(mem.to_dict(), settings, None, "s")
    assert restored.pinned == mem.pinned
    assert restored.recent == mem.recent
    assert restored.summary_lines == mem.summary_lines


def test_agent_compact_and_current(scripted, mock_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    scripted.script[:] = [act("list_files", {})] * 3 + ["Final Answer: ok"]
    agent = Agent(mock_config, ws, ApprovalPolicy("auto"))
    r = asyncio.run(agent.run("list"))
    assert agent.current is r.session
    n = agent.compact(r.session)
    assert n == 5
    loaded = SessionStore(ws / ".cora" / "sessions").load(r.session.id)
    assert len(loaded.memory["recent"]) == 2
    assert loaded.memory["summary_lines"]
