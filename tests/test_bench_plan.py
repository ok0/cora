from __future__ import annotations

import dataclasses
import json

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider
from cora.bench.live_tasks import LiveTask
from cora.bench.plan import BUDGET_REMINDER, PLAN_NOTE, build_plan, plan_markdown
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config


def _cfg() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
                {
                    "id": "mock/strong",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def T(i: int) -> LiveTask:
    return LiveTask(f"t{i}", "explore", "q", {"f.txt": "x"}, answer_regex="x")


PLAN_OPTS = [
    "--models", "mock/cheap", "--protocols", "react",
    "--tasks", "explore_find_port,explore_count_todos",
    "--repeats", "3", "--max-iterations", "4", "--max-task-cost", "0.10",
]


def test_plan_hand_calculation() -> None:
    plan = build_plan(
        _cfg(),
        tasks=[T(1), T(2)],
        models=["mock/cheap"],
        protocols=["react"],
        arms=None,
        max_iterations=4,
        max_task_cost_usd=0.10,
        max_cost_usd=0.30,
        repeats=3,
    )
    assert plan.cells[0].per_run_usd == pytest.approx(0.072192)
    assert plan.total_usd == pytest.approx(0.433152)
    assert plan.exceeds is True
    assert plan.suggest_repeats() == 2


def test_plan_cli_no_network(no_network, tmp_path, cfg_file) -> None:
    result = CliRunner().invoke(
        app, ["bench", "plan", "-c", str(cfg_file), "-w", str(tmp_path), *PLAN_OPTS]
    )
    assert result.exit_code == 0, result.stderr
    out = result.stdout
    assert "| - | mock/cheap | react | explore_find_port | 3 |" in out
    assert "total_max_usd: 0.433152" in out
    assert "OVER CAP" in out
    assert "suggested --repeats: 2" in out
    assert PLAN_NOTE in out
    assert BUDGET_REMINDER in out
    assert ScriptedProvider.calls == []
    assert no_network == []


def test_plan_ab_arms(tmp_path, cfg_file) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench", "plan", "-c", str(cfg_file), "-w", str(tmp_path),
            "--ab", "deleg-off,strong-only,auto-routed", "--models", "mock/cheap",
            "--tasks", "query_client_timeout", "--repeats", "3", "--max-iterations", "4",
            "--max-task-cost", "0.10",
        ],
    )
    assert result.exit_code == 0, result.stderr
    out = result.stdout
    assert "| mock/cheap |" in out
    assert "| mock/strong |" in out
    assert "| auto |" in out
    assert "total_max_usd: 0.816576" in out


def test_plan_unknown_price() -> None:
    base = _cfg()
    free = dataclasses.replace(
        base.models[0], id="mock/free", input_usd_per_mtok=None, output_usd_per_mtok=None
    )
    cfg = dataclasses.replace(base, models=(free,))
    plan = build_plan(
        cfg,
        tasks=[T(1)],
        models=["mock/free"],
        protocols=["react"],
        arms=None,
        max_iterations=4,
        max_task_cost_usd=0.10,
        max_cost_usd=0.30,
        repeats=1,
    )
    md = plan_markdown(plan)
    assert "unbounded/unknown" in md
    assert "no price in cora.toml for: mock/free" in md


def test_preestimate_refuses_before_calls(tmp_path, cfg_file, scripted) -> None:
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "-c", str(cfg_file), "-w", str(tmp_path), *PLAN_OPTS,
            "--repeats", "5", "--out", str(out),
        ],
    )
    assert result.exit_code == 2
    assert "exceeds --max-cost" in result.stderr
    assert scripted.calls == []
    assert not (out / "report.json").exists()


def test_trim_to_budget(tmp_path, cfg_file, scripted) -> None:
    scripted.script.extend(["Final Answer: x"] * 4)
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "-c", str(cfg_file), "-w", str(tmp_path), *PLAN_OPTS,
            "--repeats", "5", "--trim-to-budget", "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.stderr
    obj = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert obj["trimmed"]["requested_repeats"] == 5
    assert obj["trimmed"]["used_repeats"] == 2
    assert obj["settings"]["repeats"] == 2
    assert len(obj["results"]) == 4
    assert "trimmed: --repeats 5 -> 2" in (out / "report.md").read_text(encoding="utf-8")


def test_plan_equals_preestimate(tmp_path, cfg_file, scripted) -> None:
    opts = [
        "--models", "mock/cheap", "--protocols", "react",
        "--tasks", "explore_find_port,explore_count_todos", "--repeats", "1",
        "--max-cost", "0.30", "--max-iterations", "4", "--max-task-cost", "0.10",
    ]
    plan_out = CliRunner().invoke(
        app, ["bench", "plan", "-c", str(cfg_file), "-w", str(tmp_path), *opts]
    ).stdout
    line = next(x for x in plan_out.splitlines() if x.startswith("total_max_usd: "))
    scripted.script.extend(["Final Answer: x"] * 2)
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        ["bench", "--live", "-c", str(cfg_file), "-w", str(tmp_path), *opts, "--out", str(out)],
    )
    assert result.exit_code == 0, result.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert line == f"total_max_usd: {report['budget_plan']['total_max_usd']:.6f}"


def test_no_repeats_does_not_enforce(tmp_path, cfg_file, scripted) -> None:
    scripted.script.extend(["Final Answer: x"] * 2)
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "-c", str(cfg_file), "-w", str(tmp_path),
            "--models", "mock/cheap", "--protocols", "react",
            "--tasks", "explore_find_port,explore_count_todos",
            "--max-cost", "0.05", "--max-task-cost", "0.05", "--max-iterations", "4",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "note: estimated maximum" in result.stderr
