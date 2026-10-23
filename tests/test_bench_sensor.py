from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from conftest import M16_KEYS_OFF, act
from cora.bench.live import run_live_bench
from cora.bench.live_tasks import LIVE_TASKS
from cora.bench.report import report_json, report_markdown
from cora.core.config import CoraConfig, parse_config


def fixed_config() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "fixed_usage",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": "fixed_usage",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto", **M16_KEYS_OFF},
        }
    )


def run(cfg, tmp_path: Path, **kwargs):
    base = dict(max_cost_usd=0.30, max_task_cost_usd=0.10, max_iterations=4)
    base.update(kwargs)
    return asyncio.run(run_live_bench(cfg, state_dir=tmp_path / "state", **base))


@pytest.mark.slow
def test_bench_sensor_opt_in(tmp_path, scripted):
    task = next(t for t in LIVE_TASKS if t.id == "fix_off_by_one")

    scripted.script[:] = ["Final Answer: done"]
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[task],
    )
    res = report.results[0]
    assert res.status == "failed"
    assert res.check_runs == 0
    assert len(scripted.calls) == 1
    assert report.settings["sensor"]["enabled"] is False
    assert "sensor: off" in report_markdown(report, None)

    scripted.script[:] = [
        "Final Answer: done",
        act(
            "edit_file",
            {
                "path": "rng.py",
                "old": "return list(range(a, b))",
                "new": "return list(range(a, b + 1))",
            },
        ),
        "Final Answer: fixed",
    ]
    scripted.calls.clear()
    report = run(
        fixed_config(),
        tmp_path / "on",
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[task],
        sensor=True,
    )
    res = report.results[0]
    assert res.status == "solved"
    assert res.check_runs == 2
    assert res.sensor_calls == 2
    assert res.sensor_cost_usd == pytest.approx(0.0024)
    data = json.loads(report_json(report, None))
    assert data["sensor_totals"]["extra_calls"] == 2
    assert data["settings"]["sensor"]["enabled"] is True
    assert "sensor: on" in report_markdown(report, None)
