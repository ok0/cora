from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, act
from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.tools import ApprovalPolicy
from explore_mock import ExploreMock, explore, explore_config
from mcp_serve_util import InProc, serve_cfg

AUTO_DELEG = CFG_TOML + "\n[tool_groups]\nauto_simple = true\n"
AUTO_DELEG_ON = AUTO_DELEG + "\n[delegation]\nenabled = true\n"
CORE = {"list_files", "read_file", "search", "edit_file", "write_file", "delete_file", "run_shell"}
PROMPT_ON_SHA = "3ca370f8d6997e83921a59f90c315b03ae9ed4cbfb47f6df4c50f35a0da34001"
EXPECTED = {
    "explore": [
        ("delegate_start", None),
        ("tool_call", "list_files"),
        ("delegate_end", None),
        ("tool_call", "delegate"),
    ],
    "bogus": [("tool_call", "delegate")],
}


@pytest.fixture(autouse=True)
def _reset_explore_mock() -> None:
    ExploreMock.reset()


@pytest.fixture(autouse=True)
def depth_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORA_MCP_DEPTH", "0")


def _ws_norm(text: str, root: Path) -> str:
    return text.replace(str(root), "<WS>")


def test_headless_delegate_visibility(scripted, ws, tmp_path):
    cfg = tmp_path / "cora.toml"
    cfg.write_text(AUTO_DELEG, encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    result = CliRunner().invoke(
        app,
        ["run", "hi", "--headless", "--json", "--delegate", "-w", str(ws), "-c", str(cfg)],
    )
    assert result.exit_code == 0
    # pinned absent at HEAD 1627573 (M18b wave 0); present after R8
    assert "- delegate:" in scripted.calls[0].messages[0].content


def test_run_delegate_visibility(scripted, ws, tmp_path):
    cfg = tmp_path / "cora.toml"
    cfg.write_text(AUTO_DELEG, encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    CliRunner().invoke(app, ["run", "hi", "--delegate", "-w", str(ws), "-c", str(cfg)])
    # pinned absent at HEAD 1627573 (M18b wave 0); present after R8
    assert "- delegate:" in scripted.calls[0].messages[0].content


def test_mcp_delegate_visibility(scripted, ws, tmp_path):
    scripted.script[:] = ["Final Answer: ok"]
    with InProc(serve_cfg(tmp_path, base=AUTO_DELEG_ON), ws) as srv:
        srv.initialize()
        srv.doc(srv.call("run_task", {"task": "hi"}))
        srv.close()
    # pinned absent at HEAD 1627573 (M18b wave 0); present after R8
    assert "- delegate:" in scripted.calls[0].messages[0].content


def test_delegate_disabled_tool_list(scripted, ws, tmp_path):
    cfg = tmp_path / "cora.toml"
    cfg.write_text(AUTO_DELEG, encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    CliRunner().invoke(
        app,
        ["run", "hi", "--headless", "--json", "-w", str(ws), "-c", str(cfg)],
    )
    names = set()
    for line in scripted.calls[0].messages[0].content.splitlines():
        if line.startswith("- ") and ":" in line:
            names.add(line[2:].split(":", 1)[0].strip())
    assert names == CORE


def test_delegation_on_main_prompt_golden(tmp_path):
    ExploreMock.main = ["Final Answer: done"]
    asyncio.run(Agent(explore_config(), tmp_path, ApprovalPolicy("auto")).run("main task"))
    text = _ws_norm(ExploreMock.calls[0].messages[0].content, tmp_path)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == PROMPT_ON_SHA
    ExploreMock.reset()
    ExploreMock.main = ["Final Answer: done"]
    asyncio.run(
        Agent(explore_config({"nudge": False}), tmp_path, ApprovalPolicy("auto")).run("main task")
    )
    text = _ws_norm(ExploreMock.calls[0].messages[0].content, tmp_path)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == PROMPT_ON_SHA


@pytest.mark.parametrize("scenario", ["explore", "bogus"])
def test_delegate_tool_event_order_golden(tmp_path, scenario):
    if scenario == "explore":
        ExploreMock.subs = {"qa": [act("list_files", {}), "Final Answer: A"]}
        ExploreMock.main = [explore("qa"), "Final Answer: done"]
    else:
        ExploreMock.main = [act("delegate", {"task": "x", "mode": "bogus"}), "Final Answer: done"]
    events: list[dict] = []
    agent = Agent(explore_config(), tmp_path, ApprovalPolicy("auto"), on_event=events.append)
    asyncio.run(agent.run("main task"))
    seq = [
        (e["type"], e.get("tool"))
        for e in events
        if e["type"] in ("tool_call", "delegate_start", "delegate_end", "delegate_refused")
    ]
    assert seq == EXPECTED[scenario]
