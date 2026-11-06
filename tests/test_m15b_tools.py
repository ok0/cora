from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from conftest import act
from cora.bench.e2e import load_e2e_tasks
from cora.bench.live import run_live_bench
from cora.core.observability import read_events
from cora.core.policy import (
    SHELL_ALLOW,
    PolicyEngine,
    PolicyGate,
    PolicySettings,
    Rule,
    builtin_shell_allow,
)
from cora.core.shellguard import PathGuard
from cora.core.toolchains import TOOLCHAINS
from cora.core.toolgroups import group_of
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, default_tools
from cora.core.tools.base import Workspace
from e2e_util import solve_script


def _ctx(root: Path) -> ToolContext:
    return ToolContext(Workspace(root), ApprovalPolicy("auto"))


def _snap(root: Path) -> list:
    return sorted(
        (p.relative_to(root).as_posix(), p.read_bytes() if p.is_file() else None)
        for p in root.rglob("*")
    )


def _run_factory(tmp_path: Path):
    ctx = _ctx(tmp_path)
    reg = ToolRegistry(default_tools())
    return lambda n, a: asyncio.run(reg.execute(n, a, ctx))


def test_write_creates_nested(tmp_path: Path) -> None:
    run = _run_factory(tmp_path)
    res = run("write_file", {"path": "pkg/sub/a.py", "content": "x\ny\n"})
    assert res.ok
    assert (tmp_path / "pkg/sub/a.py").read_text(encoding="utf-8") == "x\ny\n"
    assert "pkg/sub/a.py" in res.output
    assert "4 bytes" in res.output
    assert "2 lines" in res.output


def test_write_overwrites_and_appends(tmp_path: Path) -> None:
    run = _run_factory(tmp_path)
    assert run("write_file", {"path": "a.txt", "content": "a\n"}).ok
    res = run("write_file", {"path": "a.txt", "content": "b\n", "append": True})
    assert res.ok
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a\nb\n"
    assert "appended" in res.output


def _prep_refusal(root: Path, kind: str) -> str:
    if kind == "dir":
        (root / "d").mkdir()
        return "d"
    if kind == "outside":
        return "../x.txt"
    if kind == "credential":
        return ".env"
    (root / ".git").mkdir()
    return ".git/config"


@pytest.mark.parametrize("kind", ["dir", "outside", "credential", "protected"])
def test_write_refusals(tmp_path: Path, kind: str) -> None:
    rel = _prep_refusal(tmp_path, kind)
    before = _snap(tmp_path)
    res = _run_factory(tmp_path)("write_file", {"path": rel, "content": "x"})
    assert res.ok is False
    assert _snap(tmp_path) == before


def test_write_bad_append_type(tmp_path: Path) -> None:
    res = _run_factory(tmp_path)("write_file", {"path": "a.txt", "content": "x", "append": "yes"})
    assert res.ok is False


def test_delete_removes_file(tmp_path: Path) -> None:
    (tmp_path / "inventory.py").write_text("x = 1\n", encoding="utf-8")
    res = _run_factory(tmp_path)("delete_file", {"path": "inventory.py"})
    assert res.ok
    assert not (tmp_path / "inventory.py").exists()


@pytest.mark.parametrize("kind", ["dir", "missing", "outside", "credential", "protected"])
def test_delete_refusals(tmp_path: Path, kind: str) -> None:
    if kind == "missing":
        rel = "nope.py"
    else:
        rel = _prep_refusal(tmp_path, kind)
    before = _snap(tmp_path)
    res = _run_factory(tmp_path)("delete_file", {"path": rel})
    assert res.ok is False
    assert _snap(tmp_path) == before


def test_default_tool_list() -> None:
    names = [t.name for t in default_tools()]
    assert "write_file" in names
    assert "delete_file" in names
    assert group_of("write_file") == "core"
    assert group_of("delete_file") == "core"


def test_edit_file_errors_name_write_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    run = _run_factory(tmp_path)
    missing = run("edit_file", {"path": "new.py", "old": "x", "new": "y"})
    assert missing.ok is False
    assert "write_file" in missing.output
    nonempty = run("edit_file", {"path": "a.py", "old": "", "new": "z"})
    assert nonempty.ok is False
    assert "write_file" in nonempty.output


def test_policy_strict_allows_both(tmp_path: Path) -> None:
    engine = PolicyEngine(PolicySettings(), PathGuard(tmp_path, ()), strict=True)
    for tool in ("edit_file", "write_file", "delete_file"):
        assert engine.evaluate(tool, {"path": "a.py"}).decision == "allow"


def test_policy_default(tmp_path: Path) -> None:
    engine = PolicyEngine(PolicySettings(), PathGuard(tmp_path, ()), strict=False)
    write = engine.evaluate("write_file", {"path": "a.py"})
    assert write.decision == "allow"
    assert write.rule == "default:edit"
    delete = engine.evaluate("delete_file", {"path": "a.py"})
    assert delete.decision == "ask"
    assert delete.rule == "default:delete"


def test_policy_headless_delete_only_where_edit(tmp_path: Path) -> None:
    gate = PolicyGate(PolicySettings(), tmp_path)
    delete = gate.check("delete_file", {"path": "a.py"}, "policy")
    assert delete.decision == "ask"
    assert delete.final is True
    assert delete.blocked is True
    edit = gate.check("edit_file", {"path": "a.py", "old": "", "new": "x"}, "policy")
    assert edit.blocked is False

    allow_gate = PolicyGate(
        PolicySettings(rules=(Rule("u", "allow", ("delete_file",), index=1),)), tmp_path
    )
    assert allow_gate.check("delete_file", {"path": "a.py"}, "policy").blocked is False

    for path in (".git/config", "../x"):
        e = gate.check("edit_file", {"path": path, "old": "", "new": "x"}, "policy")
        d = gate.check("delete_file", {"path": path}, "policy")
        assert e.blocked is True
        assert d.blocked is True
        assert e.rule == d.rule
        assert e.rule.startswith("floor:")


def test_shell_allow_unchanged(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    allow = builtin_shell_allow(tmp_path)
    digest = hashlib.sha256("\n".join(allow).encode()).hexdigest()
    assert digest == "940dee4ff8e25831e2c77ca1f7d812ddbf7f132c5036e50cf75464a47b8d160d"
    banned = {"rm", "mv", "mkdir", "touch"}
    entries = set(SHELL_ALLOW) | {
        p for tc in TOOLCHAINS.values() for p in (*tc.commands, *tc.file_runs)
    }
    assert not any(entry.split(" ", 1)[0] in banned for entry in entries)


@pytest.mark.slow
def test_refactor_inventory_delete_file_e2e(scripted, mock_config, tmp_path: Path) -> None:
    task = {t.id: t for t in load_e2e_tasks()}["e2e_refactor_inventory"]
    steps = [s for s in solve_script(task, "reference") if "Action: run_shell" not in s]
    body = steps[:-1]
    deletes = [act("delete_file", {"path": rel}) for rel in task.reference_delete]
    scripted.script.extend(body + deletes + ["Final Answer: done"])
    state = tmp_path / "s"
    res = asyncio.run(
        run_live_bench(
            mock_config,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.30,
            max_iterations=40,
            state_dir=state,
        )
    )
    row = res.results[0]
    checks = {c["name"]: c["passed"] for c in row.grader["checks"]}
    assert checks["package_layout"] is True
    assert row.policy_denies == 0
    events = [e for p in state.rglob("events.jsonl") for e in read_events(p)]
    deleted = [
        e for e in events
        if e.get("type") == "tool_call" and e.get("tool") == "delete_file" and e.get("ok") is True
    ]
    assert deleted
