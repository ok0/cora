from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import act, with_agent, write_files
from cora.core.agent import Agent
from cora.core.react import INPUT_ERROR, parse_turn
from cora.core.tools import (
    ApprovalPolicy,
    ToolContext,
    ToolRegistry,
    ToolResult,
    Workspace,
    default_tools,
)


class SleepTool:
    description = "t"
    args_doc = "{}"
    requires_approval = False
    read_only = True

    def __init__(self, name: str, delay: float, out: str) -> None:
        self.name = name
        self.delay = delay
        self.out = out

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        await asyncio.sleep(self.delay)
        return ToolResult(True, self.out)


class BoomTool:
    description = "t"
    args_doc = "{}"
    requires_approval = False
    read_only = True

    def __init__(self, name: str) -> None:
        self.name = name

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise RuntimeError("kaboom")


class CounterTool:
    description = "t"
    args_doc = "{}"
    requires_approval = False
    read_only = True

    def __init__(self, name: str, state: dict) -> None:
        self.name = name
        self.state = state

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.state["cur"] += 1
        self.state["max"] = max(self.state["max"], self.state["cur"])
        await asyncio.sleep(0.05)
        self.state["cur"] -= 1
        return ToolResult(True, self.name)


class TrackTool:
    description = "t"
    args_doc = "{}"

    def __init__(self, name: str, log: list, read_only: bool) -> None:
        self.name = name
        self.log = log
        self.read_only = read_only
        self.requires_approval = not read_only

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        self.log.append(("start", self.name))
        await asyncio.sleep(0.05)
        self.log.append(("end", self.name))
        return ToolResult(True, self.name)


def ctx(tmp_path: Path, policy: ApprovalPolicy | None = None) -> ToolContext:
    return ToolContext(Workspace(tmp_path), policy or ApprovalPolicy("auto"))


def test_parse_turn_multi_and_single() -> None:
    text = act("read_file", {"path": "a"}) + "\n" + 'Action: search\nAction Input: {"pattern": "x"}'
    turn = parse_turn(text)
    assert [c.name for c in turn.calls] == ["read_file", "search"]
    assert turn.calls[0].args == {"path": "a"}
    assert turn.calls[1].args == {"pattern": "x"}

    assert len(parse_turn(act("list_files", {})).calls) == 1

    bad = parse_turn("Thought: t\nAction: read_file\nAction Input: oops")
    assert bad.error == INPUT_ERROR
    assert bad.calls == ()

    mixed = parse_turn(act("list_files", {}) + "\nAction: read_file\nAction Input: oops")
    assert len(mixed.calls) == 2
    assert mixed.calls[1].args is None

    final = parse_turn("Final Answer: x")
    assert final.final_answer == "x"

    many = parse_turn("\n".join(act("list_files", {}) for _ in range(10)))
    assert len(many.calls) == 8
    assert many.dropped == 2


@pytest.mark.slow
def test_execute_many_parallel_order_and_failure(tmp_path: Path) -> None:
    reg = ToolRegistry(
        [
            SleepTool("slow_a", 0.3, "A"),
            SleepTool("slow_b", 0.3, "B"),
            BoomTool("boom"),
            SleepTool("slow_c", 0.3, "C"),
        ]
    )
    t0 = time.monotonic()
    res = asyncio.run(
        reg.execute_many(
            [("slow_a", {}), ("slow_b", {}), ("boom", {}), ("slow_c", {})], ctx(tmp_path), 4
        )
    )
    assert time.monotonic() - t0 < 0.7
    assert [r.output for r in res] == ["A", "B", "error: RuntimeError: kaboom", "C"]
    assert res[2].ok is False


@pytest.mark.slow
def test_execute_many_respects_concurrency_cap(tmp_path: Path) -> None:
    state = {"cur": 0, "max": 0}
    reg = ToolRegistry([CounterTool(f"c{i}", state) for i in range(6)])
    calls = [(f"c{i}", {}) for i in range(6)]
    res = asyncio.run(reg.execute_many(calls, ctx(tmp_path), 2))
    assert state["max"] == 2
    assert [r.output for r in res] == [f"c{i}" for i in range(6)]

    state = {"cur": 0, "max": 0}
    reg = ToolRegistry([CounterTool(f"c{i}", state) for i in range(6)])
    asyncio.run(reg.execute_many(calls, ctx(tmp_path), 1))
    assert state["max"] == 1


@pytest.mark.slow
def test_mixed_calls_sequential_and_deterministic_approvals(tmp_path: Path) -> None:
    for _ in range(3):
        log: list[tuple[str, str]] = []
        reg = ToolRegistry(
            [
                TrackTool("r1", log, True),
                TrackTool("r2", log, True),
                TrackTool("r3", log, True),
                TrackTool("r4", log, True),
                TrackTool("w1", log, False),
                TrackTool("w2", log, False),
            ]
        )
        asked: list[str] = []
        policy = ApprovalPolicy(
            "ask", review=lambda req, a=asked: (a.append(req.tool), "yes")[1]
        )
        calls = [(n, {}) for n in ("r1", "r2", "w1", "r3", "r4", "w2")]
        res = asyncio.run(reg.execute_many(calls, ctx(tmp_path, policy), 4))
        assert [r.output for r in res] == ["r1", "r2", "w1", "r3", "r4", "w2"]

        assert asked == ["w1", "w2"]
        idx = {event: i for i, event in enumerate(log)}
        assert idx[("start", "w1")] > idx[("end", "r1")]
        assert idx[("start", "w1")] > idx[("end", "r2")]
        assert idx[("end", "w1")] < idx[("start", "r3")]
        assert idx[("end", "w1")] < idx[("start", "r4")]
        assert idx[("start", "w2")] > idx[("end", "r3")]
        assert idx[("start", "w2")] > idx[("end", "r4")]
        assert max(idx[("start", "r1")], idx[("start", "r2")]) < min(
            idx[("end", "r1")], idx[("end", "r2")]
        )

    log = []
    reg = ToolRegistry(
        [
            TrackTool("r1", log, True),
            TrackTool("r2", log, True),
            TrackTool("r3", log, True),
            TrackTool("r4", log, True),
            TrackTool("w1", log, False),
            TrackTool("w2", log, False),
        ]
    )
    policy = ApprovalPolicy("ask", review=lambda req: "no")
    calls = [(n, {}) for n in ("r1", "r2", "w1", "r3", "r4", "w2")]
    res = asyncio.run(reg.execute_many(calls, ctx(tmp_path, policy), 4))
    assert res[2].output.startswith("denied by user")
    assert res[3].output == "r3"


@pytest.mark.slow
def test_agent_multi_action_observations(mock_config, scripted, tmp_path: Path) -> None:
    tools = [
        SleepTool("slow_a", 0.3, "A"),
        SleepTool("slow_b", 0.3, "B"),
        BoomTool("boom"),
        SleepTool("slow_c", 0.3, "C"),
    ]
    scripted.script.extend(
        [
            "\n".join(act(n, {}) for n in ("slow_a", "slow_b", "boom", "slow_c")),
            "Final Answer: ok",
        ]
    )
    events: list[dict] = []
    agent = Agent(
        mock_config,
        tmp_path,
        ApprovalPolicy("auto"),
        tools=tools,
        on_event=events.append,
    )
    t0 = time.monotonic()
    result = asyncio.run(agent.run("hello"))
    assert time.monotonic() - t0 < 0.7
    assert result.answer == "ok"
    assert scripted.calls[1].messages[-1].content == (
        "Observation 1 (slow_a): A\n\n"
        "Observation 2 (slow_b): B\n\n"
        "Observation 3 (boom): error: RuntimeError: kaboom\n\n"
        "Observation 4 (slow_c): C"
    )
    tool_events = [e["tool"] for e in events if e["type"] == "tool_call"]
    assert tool_events == ["slow_a", "slow_b", "boom", "slow_c"]


def test_builtin_read_tools_parallel(tmp_path: Path) -> None:
    write_files(tmp_path, {"a.txt": "x\n", "b.txt": "y\n"})
    reg = ToolRegistry(default_tools())
    res = asyncio.run(
        reg.execute_many(
            [
                ("read_file", {"path": "a.txt"}),
                ("read_file", {"path": "b.txt"}),
                ("list_files", {}),
            ],
            ctx(tmp_path),
            4,
        )
    )
    assert "x" in res[0].output
    assert "y" in res[1].output
    assert "a.txt" in res[2].output


def test_prompt_mentions_batching_only_when_parallel(mock_config, scripted, tmp_path: Path) -> None:
    scripted.script.extend(["Final Answer: ok"])
    asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("hello"))
    assert "batched" in scripted.calls[0].messages[0].content

    scripted.script.extend(["Final Answer: ok"])
    scripted.calls.clear()
    serial = with_agent(mock_config, max_parallel_tools=1)
    asyncio.run(Agent(serial, tmp_path, ApprovalPolicy("auto")).run("hello"))
    content = scripted.calls[0].messages[0].content
    assert "batched" not in content
    assert "one action per response;" in content
