from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.agent import RunResult
from cora.core.config import ModelSpec
from cora.core.metering import CostMeter, format_summary
from cora.core.outcome import outcome_dict
from cora.core.state import Session, StopReason


def _spec(cache_price: float | None = 0.1) -> ModelSpec:
    return ModelSpec(
        "mock/cheap",
        "scripted",
        "cheap",
        1.0,
        2.0,
        cache_read_usd_per_mtok=cache_price,
    )


def _result(summary: dict) -> RunResult:
    return RunResult(
        Session(id="s", task="t"),
        "ans",
        StopReason.FINAL_ANSWER,
        summary,
        Path("x"),
    )


def test_cost_with_cached_price():
    meter = CostMeter()
    rec = meter.record(_spec(), "cheap", "react", 1000, 100, cached_input_tokens=600)
    assert rec.cost_usd == pytest.approx(0.00066)
    rec0 = meter.record(_spec(), "cheap", "react", 1000, 100, cached_input_tokens=0)
    assert rec0.cost_usd == pytest.approx(0.0012)


def test_cost_unknown_cache_price_unchanged():
    meter = CostMeter()
    rec = meter.record(_spec(None), "cheap", "react", 1000, 100, cached_input_tokens=600)
    assert rec.cost_usd == pytest.approx(0.0012)
    assert rec.cached_input_tokens == 600


def test_cached_clamped():
    meter = CostMeter()
    rec = meter.record(_spec(), "cheap", "react", 1000, 100, cached_input_tokens=5000)
    assert rec.cost_usd == pytest.approx(1000 * 0.1 / 1e6 + 100 * 2 / 1e6)
    assert rec.cost_usd >= 0


def test_provider_cost_wins():
    meter = CostMeter()
    rec = meter.record(
        _spec(), "cheap", "react", 1000, 100, cost_usd=0.5, cached_input_tokens=600
    )
    assert rec.cost_usd == pytest.approx(0.5)
    assert rec.cost_source == "provider_usage"


def test_summary_and_format():
    meter = CostMeter()
    meter.record(_spec(), "cheap", "react", 1000, 100, cached_input_tokens=600)
    summary = meter.summary()
    assert summary["by_model"]["mock/cheap"]["cached_input_tokens"] == 600
    assert "cached=600" in format_summary(summary)

    plain = CostMeter()
    plain.record(_spec(), "cheap", "react", 1000, 100)
    plain_summary = plain.summary()
    assert "cached_input_tokens" not in plain_summary["by_model"]["mock/cheap"]
    assert "cached=" not in format_summary(plain_summary)


def test_outcome_tokens():
    meter = CostMeter()
    meter.record(_spec(), "cheap", "react", 1000, 100, cached_input_tokens=600)
    out = outcome_dict(_result(meter.summary()), None, wall_s=0.0)
    assert out["tokens"] == {"in": 1000, "out": 100, "cached": 600}

    plain = CostMeter()
    plain.record(_spec(), "cheap", "react", 1000, 100)
    out_plain = outcome_dict(_result(plain.summary()), None, wall_s=0.0)
    assert set(out_plain["tokens"]) == {"in", "out"}


def test_from_list_old_records():
    data = [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "model": "mock/cheap",
            "tier": "cheap",
            "purpose": "react",
            "input_tokens": 1000,
            "output_tokens": 100,
            "cost_usd": 0.0012,
        }
    ]
    meter = CostMeter.from_list(data)
    assert meter.records[0].cached_input_tokens == 0
