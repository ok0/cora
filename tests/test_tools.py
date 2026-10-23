from __future__ import annotations

import asyncio
import os

from cora.core.tools import (
    ApprovalPolicy,
    ListFilesTool,
    ToolContext,
    ToolRegistry,
    Workspace,
    default_tools,
)


def _registry() -> ToolRegistry:
    return ToolRegistry(default_tools())


def _ctx(ws, approval: ApprovalPolicy) -> ToolContext:
    return ToolContext(Workspace(ws), approval)


def _fail(action: str) -> bool:
    raise AssertionError(f"approval must not be requested for: {action}")


def test_ask_mode_blocks_edit(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    prompts: list[str] = []
    ctx = _ctx(ws, ApprovalPolicy("ask", ask=lambda s: prompts.append(s) or False))
    res = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}, ctx)
    )
    assert res.ok is False
    assert "denied by user" in res.output
    assert (ws / "a.txt").read_text(encoding="utf-8") == "hello"
    assert prompts[0].startswith("edit_file")


def test_ask_mode_blocks_shell(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    prompts: list[str] = []
    ctx = _ctx(ws, ApprovalPolicy("ask", ask=lambda s: prompts.append(s) or False))
    res = asyncio.run(_registry().execute("run_shell", {"command": "echo hi"}, ctx))
    assert res.ok is False
    assert "denied by user" in res.output
    assert prompts[0].startswith("run_shell")


def test_ask_mode_without_callback_denies(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("ask"))
    res = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}, ctx)
    )
    assert res.ok is False


def test_read_does_not_ask(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("ask", ask=_fail))
    res = asyncio.run(_registry().execute("read_file", {"path": "a.txt"}, ctx))
    assert res.ok is True


def test_outside_paths_denied(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    os.symlink(tmp_path / "outside.txt", ws / "link")
    ctx = _ctx(ws, ApprovalPolicy("ask", ask=_fail))
    cases = [
        ("read_file", {"path": "../x.txt"}),
        ("read_file", {"path": "/etc/hosts"}),
        ("edit_file", {"path": "../x.txt", "old": "", "new": "y"}),
        ("run_shell", {"command": "cat ../secret"}),
        ("read_file", {"path": "link"}),
    ]
    for name, args in cases:
        res = asyncio.run(_registry().execute(name, args, ctx))
        assert res.ok is False, name
        assert "outside workspace" in res.output, name


def test_edit_unique_match(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "d.txt"
    target.write_text("x\nx\n", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("auto"))
    dup = asyncio.run(
        _registry().execute("edit_file", {"path": "d.txt", "old": "x", "new": "y"}, ctx)
    )
    assert dup.ok is False
    assert "occurs 2 times" in dup.output
    target.write_text("one\ntwo\n", encoding="utf-8")
    ok = asyncio.run(
        _registry().execute("edit_file", {"path": "d.txt", "old": "two", "new": "2"}, ctx)
    )
    assert ok.ok is True
    assert target.read_text(encoding="utf-8") == "one\n2\n"


def test_search_skips_reference(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".reference").mkdir(parents=True)
    (ws / ".reference" / "doc.txt").write_text("NEEDLE\n", encoding="utf-8")
    (ws / "src").mkdir()
    (ws / "src" / "x.py").write_text("NEEDLE = 1\n", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("auto"))
    res = asyncio.run(_registry().execute("search", {"pattern": "NEEDLE"}, ctx))
    assert res.ok is True
    assert "src/x.py:1" in res.output
    assert ".reference" not in res.output


def test_list_files_skips_reference(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".reference").mkdir(parents=True)
    (ws / ".reference" / "doc.txt").write_text("doc\n", encoding="utf-8")
    (ws / "keep.txt").write_text("keep\n", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("auto"))
    res = asyncio.run(ListFilesTool().run({"path": "."}, ctx))
    assert "keep.txt" in res.output
    assert ".reference" not in res.output


def test_edit_review_shows_diff_and_always(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    reqs = []
    ctx = _ctx(ws, ApprovalPolicy("ask", review=lambda r: reqs.append(r) or "always"))
    r1 = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}, ctx)
    )
    r2 = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "bye", "new": "ciao"}, ctx)
    )
    assert r1.ok is True
    assert r2.ok is True
    assert len(reqs) == 1
    assert reqs[0].tool == "edit_file"
    assert "-hello" in reqs[0].detail and "+bye" in reqs[0].detail
    assert (ws / "a.txt").read_text(encoding="utf-8") == "ciao\n"


def test_shell_always_is_per_command(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    reqs = []
    ctx = _ctx(ws, ApprovalPolicy("ask", review=lambda r: reqs.append(r) or "always"))
    asyncio.run(_registry().execute("run_shell", {"command": "echo hi"}, ctx))
    asyncio.run(_registry().execute("run_shell", {"command": "echo hi"}, ctx))
    asyncio.run(_registry().execute("run_shell", {"command": "echo bye"}, ctx))
    assert len(reqs) == 2
    assert reqs[0].detail == "$ echo hi"


def test_edit_errors_before_approval(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("ask", ask=_fail, review=lambda r: _fail(r.summary)))
    nf = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "zzz", "new": "y"}, ctx)
    )
    assert nf.ok is False
    assert "not found in a.txt" in nf.output
    assert "read_file" in nf.output
    missing = asyncio.run(
        _registry().execute("edit_file", {"path": "b.txt", "old": "x", "new": "y"}, ctx)
    )
    assert missing.ok is False
    assert "does not exist" in missing.output
    (ws / "a.txt").write_text("x\nx\n", encoding="utf-8")
    dup = asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "x", "new": "y"}, ctx)
    )
    assert dup.ok is False
    assert "occurs 2 times" in dup.output
    assert "lines 1, 2" in dup.output


def test_edit_records_originals(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    ctx = _ctx(ws, ApprovalPolicy("auto"))
    asyncio.run(
        _registry().execute("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}, ctx)
    )
    asyncio.run(_registry().execute("edit_file", {"path": "n.txt", "old": "", "new": "new"}, ctx))
    assert ctx.originals == {"a.txt": "hello", "n.txt": None}
