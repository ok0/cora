from __future__ import annotations

import asyncio

from conftest import act, run_repl
from cora.core.agent import Agent
from cora.core.tools import ApprovalPolicy


def test_theme_command(scripted, ws, cfg_file) -> None:
    out = run_repl(
        ws, cfg_file, ["/theme", "/theme mono", "/theme nope", "/theme", "/theme a b", "/exit"]
    )
    markers = [
        "theme: default (available: default, dark, light, mono)",
        "theme: mono (this session only",
        "error: unknown theme 'nope'",
        "theme: mono (available:",
        "error: usage: /theme",
    ]
    pos = 0
    for marker in markers:
        idx = out.index(marker, pos)
        pos = idx + len(marker)


def test_expand_without_collapsed(scripted, ws, cfg_file) -> None:
    out = run_repl(ws, cfg_file, ["/expand", "/expand x", "/exit"])
    assert "No collapsed tool result to expand" in out
    assert "error: usage: /expand" in out


def test_agent_tool_output_hook(scripted, mock_config, tmp_path) -> None:
    events: list[dict] = []
    outs: list[str] = []
    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    asyncio.run(
        Agent(
            mock_config,
            tmp_path,
            ApprovalPolicy("auto"),
            on_event=events.append,
            on_tool_output=outs.append,
        ).run("list")
    )
    assert len(outs) == 1
    calls = [e for e in events if e["type"] == "tool_call"]
    assert calls and "output" not in calls[0]
