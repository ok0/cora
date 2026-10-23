from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from conftest import act
from cora.bench.live import run_live_bench
from cora.bench.live_tasks import MULTI_TASKS, PYTEST_CHECK, LiveTask
from cora.core.config import CoraConfig, parse_config

RNG_BUG = "def inclusive_range(a, b):\n    return list(range(a, b))\n"
VISIBLE = (
    "from rng import inclusive_range\n\n\n"
    "def test_visible():\n    assert inclusive_range(1, 3) == [1, 2, 3]\n"
)
HIDDEN = (
    "# HIDDEN_GRADER_MARKER\n"
    "from rng import inclusive_range\n\n\n"
    "def test_hidden():\n    assert inclusive_range(1, 3) == [1, 2, 3]\n"
)
T = LiveTask(
    id="auto_rng",
    kind="bugfix",
    prompt="Fix rng.py so the tests pass.",
    files={"rng.py": RNG_BUG, "test_visible.py": VISIBLE},
    check=PYTEST_CHECK + " test_hidden.py",
    check_files={"test_hidden.py": HIDDEN},
)


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
            "agent": {"approval": "auto"},
        }
    )


def run(cfg, tmp_path: Path, **kwargs):
    base = dict(max_cost_usd=0.30, max_task_cost_usd=0.10, max_iterations=4)
    base.update(kwargs)
    return asyncio.run(run_live_bench(cfg, state_dir=tmp_path / "state", **base))


@pytest.mark.slow
def test_auto_stop_before_gate_zero_check_runs(tmp_path, scripted):
    scripted.script[:] = [act("read_file", {"path": "rng.py"})] * 4
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T],
        sensor=True,
        sensor_source="auto",
        max_iterations=2,
    )
    res = report.results[0]
    assert report.settings["sensor"]["no_check_tasks"] == []
    assert res.check_runs == 0
    assert res.status != "solved"
    assert res.stop_reason != "final_answer"


@pytest.mark.slow
def test_auto_no_check_task_listed(tmp_path, scripted):
    scripted.script[:] = ["Final Answer: x"]
    multi = MULTI_TASKS[0]
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[multi],
        sensor=True,
        sensor_source="auto",
    )
    res = report.results[0]
    assert report.settings["sensor"]["no_check_tasks"] == ["query_client_timeout"]
    assert res.check_runs == 0
