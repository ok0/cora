from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cora.bench.live import run_live_bench
from cora.bench.live_tasks import select_tasks
from cora.core.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.live
def test_live_smoke_one_task(tmp_path):
    cfg = load_config(REPO_ROOT / "cora.toml")
    report = asyncio.run(
        run_live_bench(
            cfg,
            models=[cfg.bench.models[0]],
            protocols=["native"],
            tasks=select_tasks(["explore_find_port"]),
            max_cost_usd=0.02,
            max_task_cost_usd=0.02,
            max_iterations=6,
            state_dir=tmp_path / "state",
        )
    )
    assert len(report.results) == 1
    assert report.total_cost_usd <= 0.02
    assert report.results[0].status in {"solved", "failed", "stopped_budget"}
