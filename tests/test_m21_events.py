from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

from conftest import act
from cora.core.agent import Agent
from cora.core.config import CacheSettings, ContextSettings, MemorySettings
from cora.core.memory import WorkingMemory
from cora.core.observability import read_events
from cora.core.tools import ApprovalPolicy
from cora.core.types import Message

ROOT = Path(__file__).resolve().parents[1]


def cfg_for(mock_config: Any, **ctx: Any) -> Any:
    return dataclasses.replace(
        mock_config,
        context=ContextSettings(**ctx),
        memory=MemorySettings(
            context_budget_tokens=100_000, keep_last_messages=8, max_observation_chars=4000
        ),
    )


def run_steps(ws: Path, scripted: Any, cfg: Any, steps: list, task: str = "task") -> tuple:
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend(steps)
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))
    return r, list(scripted.calls)


def small_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("".join(f"line {i}\n" for i in range(50)), encoding="utf-8")
    return ws


def test_memory_dedupe_count():
    mem = WorkingMemory(MemorySettings(), dedupe_reads=True)
    for i in range(3):
        mem.add(Message(role="tool", content=f"read {i}"), read_path="a.txt")
    assert mem.drain_context_counts() == (2, 0)
    assert mem.drain_context_counts() == (0, 0)

    off = WorkingMemory(MemorySettings(), dedupe_reads=False)
    for i in range(3):
        off.add(Message(role="tool", content=f"read {i}"), read_path="a.txt")
    assert off.drain_context_counts() == (0, 0)


def test_memory_compressed_count():
    mem = WorkingMemory(
        MemorySettings(keep_last_messages=2, context_budget_tokens=100_000), compress_chars=50
    )
    for i in range(5):
        mem.add(Message(role="tool", content="x" * 400 + str(i)))
    mem.build("sys")
    assert mem.drain_context_counts()[1] == 3
    mem.build("sys")
    assert mem.drain_context_counts() == (0, 0)


def test_agent_read_dedupe_event(tmp_path, scripted, mock_config, no_network):
    ws = small_ws(tmp_path)
    steps = [
        act("read_file", {"path": "a.txt"}),
        act("read_file", {"path": "a.txt"}),
        "Final Answer: ok",
    ]
    r, _ = run_steps(ws, scripted, cfg_for(mock_config, dedupe_reads=True), steps)
    events = [e for e in read_events(r.log_path) if e["type"] == "read_dedupe"]
    assert len(events) == 1
    assert events[0]["superseded"] == 1
    assert "iteration" in events[0]


def test_agent_compress_event(tmp_path, scripted, mock_config, no_network):
    ws = small_ws(tmp_path)
    cfg = dataclasses.replace(
        mock_config,
        cache=CacheSettings(compress_observations=True, compress_chars=50),
        memory=MemorySettings(
            context_budget_tokens=100_000, keep_last_messages=2, max_observation_chars=4000
        ),
    )
    steps = [act("read_file", {"path": "a.txt", "start_line": 1 + 10 * i}) for i in range(4)]
    steps.append("Final Answer: ok")
    r, _ = run_steps(ws, scripted, cfg, steps)
    events = [e for e in read_events(r.log_path) if e["type"] == "observation_compress"]
    assert events
    assert sum(e["compressed"] for e in events) >= 1


def test_agent_off_no_new_events(tmp_path, scripted, mock_config, no_network):
    ws = small_ws(tmp_path)
    steps = [
        act("read_file", {"path": "a.txt"}),
        act("read_file", {"path": "a.txt"}),
        "Final Answer: ok",
    ]
    r, _ = run_steps(ws, scripted, cfg_for(mock_config), steps)
    types = {e["type"] for e in read_events(r.log_path)}
    assert "read_dedupe" not in types
    assert "observation_compress" not in types
    assert "repo_map" not in types


def test_repo_map_event_tokens(tmp_path, scripted, mock_config, no_network):
    ws = small_ws(tmp_path)
    r, _ = run_steps(ws, scripted, cfg_for(mock_config, repo_map=True), ["Final Answer: ok"])
    events = [e for e in read_events(r.log_path) if e["type"] == "repo_map"]
    assert len(events) == 1
    tokens = events[0]["tokens"]
    assert isinstance(tokens, int)
    assert 0 < tokens <= events[0]["chars"]


def test_docs_mention_m21_events():
    for rel in ("USAGE.md", ".docs/architecture.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "read_dedupe" in text, rel
        assert "observation_compress" in text, rel
