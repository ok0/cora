from __future__ import annotations

import asyncio

import pytest

from conftest import act
from cora.core.agent import Agent
from cora.core.config import ModelSpec
from cora.core.metering import estimate_cost, format_summary
from cora.core.observability import read_events
from cora.core.tools import ApprovalPolicy


def test_estimate_cost():
    spec = ModelSpec("m", "p", "cheap", 1.0, 2.0)
    assert estimate_cost(spec, 1_000_000, 500_000) == pytest.approx(2.0)


def test_summary_and_call_log(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        act("list_files", {}),
        act("list_files", {}),
        "Final Answer: ok",
    ]
    r = asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("list files"))
    summary = r.summary
    assert summary["calls"] == 3 == len(scripted.calls)
    assert any(
        model_id in summary["by_model"] and summary["by_model"][model_id]["input_tokens"] > 0
        for model_id in ("mock/strong", "mock/cheap")
    )
    llm_events = [e for e in read_events(r.log_path) if e["type"] == "llm_call"]
    assert len(llm_events) == 3
    for e in llm_events:
        assert "model" in e
        assert "input_tokens" in e
        assert "output_tokens" in e
        assert "cost_usd" in e
    text = format_summary(summary)
    assert "calls: 3" in text
    assert "total_estimated_cost_usd:" in text
