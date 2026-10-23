from __future__ import annotations

import pytest
from typer.testing import CliRunner

from conftest import COMPLEX_PROMPT, FIXED_CFG_TOML, act, run_repl
from cora.cli.main import app
from cora.core.config import ModelSpec
from cora.core.metering import CostMeter, format_summary


def test_meter_delegated_summary():
    cheap = ModelSpec("mock/cheap", "scripted", "cheap", 1.0, 2.0)
    unpriced = ModelSpec("u/x", "p", "strong", None, None)
    meter = CostMeter()
    meter.record(cheap, "cheap", "react", 1000, 100)
    meter.record(cheap, "cheap", "delegate", 1000, 100)
    meter.record(unpriced, "strong", "delegate", 10, 1)
    summary = meter.summary()
    assert summary["delegated"] == {
        "calls": 2,
        "input_tokens": 1010,
        "output_tokens": 101,
        "cost_usd": pytest.approx(0.0012),
        "price_known": False,
    }
    assert "delegated (sub-agents): calls=2 in=1010 out=101 cost=unknown" in format_summary(summary)


def test_cost_report_multi_model_and_delegation(tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = tmp_path / "c.toml"
    cfg.write_text(FIXED_CFG_TOML + "\n[delegation]\nenabled = true\n", encoding="utf-8")
    scripted.script.extend(
        [
            act("delegate", {"task": "look"}),
            "Final Answer: sub summary",
            "Final Answer: a1",
            "Final Answer: a2",
        ]
    )
    out = run_repl(
        ws,
        cfg,
        ["hello", "/model strong foo/bar", COMPLEX_PROMPT, "/cost", "/exit"],
    )
    assert "model mock/cheap: calls=3 in=3000 out=300 cost=$0.003600" in out
    assert "model foo/bar: calls=1 in=1000 out=100 cost=unknown" in out
    assert "delegated (sub-agents): calls=1 in=1000 out=100 cost=$0.001200" in out
    assert "total_estimated_cost_usd: 0.003600" in out
    assert "unknown_cost_calls: 1" in out
    assert out.count("delegated (sub-agents): calls=1") == 2


def test_cost_cap_cli_exit_code(tmp_path, scripted):
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = tmp_path / "c.toml"
    cfg.write_text(FIXED_CFG_TOML, encoding="utf-8")
    scripted.script.extend([act("list_files", {})] * 5)
    result = CliRunner().invoke(
        app,
        [
            "run",
            "hello",
            "-w",
            str(ws),
            "-c",
            str(cfg),
            "--approval",
            "auto",
            "--max-cost",
            "0.0015",
        ],
    )
    assert result.exit_code == 1
    assert len(scripted.calls) == 2
    assert "stop_reason: cost_limit" in result.stderr
