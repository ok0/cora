from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from conftest import act
from cora.core.config import DelegationSettings, MemorySettings
from cora.core.delegation import run_subagent
from cora.core.memory import WorkingMemory, compress_text
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, ToolResult, Workspace
from cora.core.types import Message


def _settings(keep_last: int = 2) -> MemorySettings:
    return MemorySettings(
        context_budget_tokens=100_000, keep_last_messages=keep_last, max_observation_chars=4000
    )


def _sequence(m: WorkingMemory) -> None:
    m.add(Message("assistant", "A1"))
    m.add(Message("user", "Observation: " + "x" * 2000))
    m.add(Message("assistant", "A2"))
    m.add(Message("user", "Observation: short"))
    m.add(Message("assistant", "y" * 2000))
    m.add(Message("tool", "z" * 2000, tool_call_id="c"))
    m.add(Message("assistant", "A4"))
    m.add(Message("user", "Observation: " + "w" * 2000))


def _contents(messages: list[Message]) -> list[str]:
    return [m.content for m in messages]


def test_compress_text() -> None:
    out = compress_text("a" * 1000, 200)
    assert out.startswith("a" * 100)
    assert "[compressed: 800 chars omitted]" in out
    assert out.endswith("a" * 100)
    assert len(out) < 1000
    assert compress_text("b" * 100, 200) == "b" * 100
    assert compress_text(out, 200) == out


def test_memory_compresses_old_only() -> None:
    m = WorkingMemory(_settings(), compress_chars=200)
    _sequence(m)
    result = m.build("SYS")
    contents = _contents(result)
    assert result[0].content == "SYS"
    first_obs = next(c for c in contents if c.startswith("Observation: x"))
    assert "[compressed: " in first_obs
    assert len(first_obs) < len("Observation: " + "x" * 2000)
    assert "Observation: short" in contents
    assert "y" * 2000 in contents
    assert result[6].role == "tool"
    assert "[compressed: " in result[6].content
    assert contents[-1] == "Observation: " + "w" * 2000


def test_latest_observation_never_compressed() -> None:
    m = WorkingMemory(_settings(keep_last=0), compress_chars=200)
    m.add(Message("user", "Observation: " + "x" * 2000))
    m.add(Message("assistant", "t"))
    m.add(Message("user", "Observation: " + "w" * 2000))
    result = m.build("SYS")
    assert result[-1].content == "Observation: " + "w" * 2000
    assert "[compressed: " in result[1].content


def test_latest_read_protected() -> None:
    m = WorkingMemory(_settings(), compress_chars=200)
    m.add(Message("user", "Observation: " + "x" * 2000), read_path="a.txt")
    m.add(Message("assistant", "t1"))
    m.add(Message("user", "Observation: " + "y" * 2000), read_path="a.txt")
    m.add(Message("assistant", "t2"))
    m.add(Message("user", "Observation: " + "f" * 2000))
    m.add(Message("assistant", "t3"))
    result = m.build("SYS")
    contents = _contents(result)
    assert "[compressed: " in contents[1]
    assert "Observation: " + "y" * 2000 in contents

    d = WorkingMemory(_settings(), dedupe_reads=True, compress_chars=200)
    d.add(Message("user", "Observation: " + "x" * 2000), read_path="a.txt")
    d.add(Message("assistant", "t1"))
    d.add(Message("user", "Observation: " + "y" * 2000), read_path="a.txt")
    d.add(Message("assistant", "t2"))
    d.add(Message("user", "Observation: " + "f" * 2000))
    d.add(Message("assistant", "t3"))
    dresult = d.build("SYS")
    dcontents = _contents(dresult)
    assert dcontents[1] == "[superseded: a.txt read again later]"
    assert "Observation: " + "y" * 2000 in dcontents


def test_off_is_identity() -> None:
    plain = WorkingMemory(_settings())
    off = WorkingMemory(_settings(), compress_chars=0)
    _sequence(plain)
    _sequence(off)
    assert plain.build("SYS") == off.build("SYS")
    assert plain.to_dict() == off.to_dict()
    assert "read_paths" not in off.to_dict()


def test_roundtrip_keeps_setting() -> None:
    m = WorkingMemory(_settings(), compress_chars=200)
    _sequence(m)
    restored = WorkingMemory.from_dict(m.to_dict(), _settings(), None, "s", compress_chars=200)
    assert restored.compress_chars == 200


class _FakeReadTool:
    name = "list_files"
    description = "fake read-only listing"
    args_doc = "{}"
    requires_approval = False
    read_only = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(True, "q" * 2000)


def _run_sub(tmp_path: Path, compress_chars: int, keep_last: int) -> list[list[Message]]:
    recorded: list[list[Message]] = []
    replies = [act("list_files", {}), act("list_files", {}), "Final Answer: ok"]

    async def call(messages: list[Message]) -> str:
        recorded.append(list(messages))
        return replies[len(recorded) - 1]

    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"))
    asyncio.run(
        run_subagent(
            "do it",
            call=call,
            tools=ToolRegistry([_FakeReadTool()]),
            ctx=ctx,
            system_prompt="SYS",
            settings=DelegationSettings(),
            tokens_used=lambda: 0,
            cost_exceeded=lambda: False,
            on_tool=lambda *a: None,
            max_observation_chars=4000,
            compress_chars=compress_chars,
            keep_last=keep_last,
        )
    )
    return recorded


def test_subagent_compresses(tmp_path: Path) -> None:
    recorded = _run_sub(tmp_path, compress_chars=200, keep_last=2)
    third = recorded[2]
    assert "[compressed: " in third[3].content
    assert third[-1].content == "Observation: " + "q" * 2000


def test_subagent_off_has_no_marker(tmp_path: Path) -> None:
    recorded = _run_sub(tmp_path, compress_chars=0, keep_last=2)
    assert all("[compressed: " not in m.content for call in recorded for m in call)
