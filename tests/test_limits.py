from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from conftest import act, with_agent
from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.observability import read_events
from cora.core.state import AgentState, StopReason
from cora.core.tools import ApprovalPolicy


def test_max_iterations_stop(scripted, mock_config, tmp_path):
    cfg = with_agent(mock_config, max_iterations=3)
    scripted.script[:] = [act("list_files", {})] * 10
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("list"))
    assert r.stop_reason == StopReason.MAX_ITERATIONS
    assert r.session.state == AgentState.STOPPED
    stops = [e for e in read_events(r.log_path) if e["type"] == "stop"]
    assert stops[-1]["reason"] == "max_iterations"


def test_cost_limit_stop(scripted, mock_config, tmp_path):
    cfg = with_agent(mock_config, max_cost_usd=1e-9)
    scripted.script[:] = [act("list_files", {})] * 10
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("list"))
    assert r.stop_reason == StopReason.COST_LIMIT
    assert r.summary["calls"] == 1


def test_cli_prints_stop_reason(scripted, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfgpath = tmp_path / "cora.toml"
    cfgpath.write_text(
        """
[[models]]
id = "mock/cheap"
provider = "scripted"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[[models]]
id = "mock/strong"
provider = "scripted"
tier = "strong"
input_usd_per_mtok = 5.0
output_usd_per_mtok = 10.0

[agent]
max_iterations = 2
""",
        encoding="utf-8",
    )
    scripted.script[:] = [act("list_files", {})] * 5
    result = CliRunner().invoke(
        app,
        ["run", "list files", "-w", str(ws), "-c", str(cfgpath), "--approval", "auto"],
    )
    assert result.exit_code == 1, result.output
    assert "stop_reason: max_iterations" in result.output
    assert "== CORA cost summary ==" in result.output
