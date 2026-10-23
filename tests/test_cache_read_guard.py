from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cora.core.tools import ApprovalPolicy
from cora.core.tools.base import ToolContext, Workspace
from cora.core.tools.builtin import default_tools
from cora.core.tools.registry import ToolRegistry
from repo_fixture import SECRET


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    for rel in (".env", ".env.local", "id_rsa"):
        (ws / rel).write_text(f"TOKEN={SECRET}\n", encoding="utf-8")
    (ws / ".env.example").write_text("TOKEN=example\n", encoding="utf-8")
    (ws / "notes.txt").write_text("hello\n", encoding="utf-8")
    return ws


def _read(ws: Path, rel: str, mode: str = "auto"):
    ctx = ToolContext(Workspace(ws), ApprovalPolicy(mode))
    return asyncio.run(ToolRegistry(default_tools()).execute("read_file", {"path": rel}, ctx))


@pytest.mark.parametrize("mode", ["auto", "ask", "deny"])
@pytest.mark.parametrize("rel", [".env", ".env.local", "id_rsa"])
def test_read_file_denies_credential_files(tmp_path, rel, mode):
    r = _read(_ws(tmp_path), rel, mode)
    assert r.ok is False
    assert r.output == f"denied: credential file: {rel}"
    assert SECRET not in r.output


@pytest.mark.parametrize(
    ("rel", "text"), [(".env.example", "TOKEN=example"), ("notes.txt", "hello")]
)
def test_read_file_allows_exempt_and_normal(tmp_path, rel, text):
    r = _read(_ws(tmp_path), rel)
    assert r.ok is True
    assert text in r.output
