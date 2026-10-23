from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from conftest import act, run_repl
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, Workspace, default_tools


def _ctx(root: Path) -> ToolContext:
    def ask(_: str) -> bool:
        raise AssertionError("approval should not be requested")

    return ToolContext(Workspace(root), ApprovalPolicy("ask", ask=ask))


def _write(reg: ToolRegistry, ctx: ToolContext, todos: Any):
    return asyncio.run(reg.execute("todo_write", {"todos": todos}, ctx))


def test_todo_write_replaces(tmp_path):
    reg = ToolRegistry(default_tools())
    ctx = _ctx(tmp_path)
    res = _write(
        reg,
        ctx,
        [
            {"content": "a", "status": "in_progress"},
            {"content": "b", "status": "pending"},
        ],
    )
    assert res.ok
    assert ctx.todos.render() == "[~] a\n[ ] b"
    res = _write(reg, ctx, [{"content": "c", "status": "completed"}])
    assert res.ok
    assert ctx.todos.render() == "[x] c"


def test_todo_two_in_progress_rejected(tmp_path):
    reg = ToolRegistry(default_tools())
    ctx = _ctx(tmp_path)
    assert _write(reg, ctx, [{"content": "a", "status": "pending"}]).ok
    before = ctx.todos.render()
    res = _write(
        reg,
        ctx,
        [
            {"content": "x", "status": "in_progress"},
            {"content": "y", "status": "in_progress"},
        ],
    )
    assert res.ok is False
    assert "at most one item may be in_progress" in res.output
    assert ctx.todos.render() == before


def test_todo_bad_input(tmp_path):
    reg = ToolRegistry(default_tools())
    ctx = _ctx(tmp_path)
    res = _write(reg, ctx, [{"content": "a", "status": "done"}])
    assert res.ok is False
    assert "invalid arguments" in res.output
    for args in ({"todos": [], "x": 1}, {"todos": "a"}):
        res = asyncio.run(reg.execute("todo_write", args, ctx))
        assert res.ok is False
        assert "invalid arguments" in res.output


def test_repl_todo_command(scripted, ws, cfg_file):
    scripted.script[:] = [
        act(
            "todo_write",
            {
                "todos": [
                    {"content": "a", "status": "in_progress"},
                    {"content": "b", "status": "pending"},
                ]
            },
        ),
        "Final Answer: ok",
    ]
    out = run_repl(ws, cfg_file, ["/todo", "plan work", "/todo", "/exit"], approval="ask")
    assert "No TODO items." in out
    assert "[~] a" in out
    assert "[ ] b" in out
    assert "Allow?" not in out
