from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider
from cora.bench.harness import format_table, run_bench
from cora.bench.live import run_live_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.report import atomic_write_text, report_json
from cora.bench.tasks import BenchTask
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config
from cora.core.errors import ProviderAccountError
from cora.core.providers import register_provider


@register_provider("cent_v2")
class CentV2Provider(ScriptedProvider):
    async def complete(self, req):
        return dataclasses.replace(await super().complete(req), cost_usd=0.01)


@register_provider("acct_v2")
class AcctV2Provider(ScriptedProvider):
    fail_at: ClassVar[int | None] = None

    async def complete(self, req):
        attempt = len(ScriptedProvider.calls) + 1
        if AcctV2Provider.fail_at is not None and attempt >= AcctV2Provider.fail_at:
            raise ProviderAccountError(402, "insufficient credits")
        return await super().complete(req)


@register_provider("killer_v2")
class KillerV2Provider(ScriptedProvider):
    kill_at: ClassVar[int | None] = None

    async def complete(self, req):
        attempt = len(ScriptedProvider.calls) + 1
        if KillerV2Provider.kill_at is not None and attempt >= KillerV2Provider.kill_at:
            raise KeyboardInterrupt
        return await super().complete(req)


@pytest.fixture(autouse=True)
def reset_hooks():
    AcctV2Provider.fail_at = None
    KillerV2Provider.kill_at = None
    yield
    AcctV2Provider.fail_at = None
    KillerV2Provider.kill_at = None


def _cfg(provider: str, in_price: float = 1.0, out_price: float = 2.0) -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": provider,
                    "tier": "cheap",
                    "input_usd_per_mtok": in_price,
                    "output_usd_per_mtok": out_price,
                }
            ],
            "agent": {"approval": "auto", "react_max_tokens": 1024},
        }
    )


def T(i: int, rx: str = "ok") -> LiveTask:
    return LiveTask(f"t{i}", "explore", "q", {"f.txt": "x"}, answer_regex=rx)


def _run(cfg: CoraConfig, tmp_path: Path, **kwargs):
    base = dict(max_cost_usd=0.30, max_task_cost_usd=0.10, max_iterations=4)
    base.update(kwargs)
    return asyncio.run(run_live_bench(cfg, state_dir=tmp_path / "state", **base))


def test_cli_repeats_invalid(cfg_file) -> None:
    path = str(cfg_file)
    for args in (
        ["bench", "--repeats", "0", "-c", path],
        ["bench", "--repeats", "abc", "-c", path],
        ["bench", "--live", "--repeats", "0", "-c", path],
    ):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2, args
        assert "--repeats" in result.stderr


def test_repeats_five_run_ids_and_seeds(tmp_path, scripted) -> None:
    scripted.script.extend(["Final Answer: ok"] * 10)
    report = _run(
        _cfg("cent_v2", 0.0, 10.0),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1), T(2)],
        repeats=5,
        seed=7,
    )
    assert len({r.run_id for r in report.results}) == 10
    for task in ("t1", "t2"):
        rs = [r for r in report.results if r.task == task]
        assert len({r.run_id for r in rs}) == 5
        assert {r.seed for r in rs} == {7, 8, 9, 10, 11}
    units = json.loads(report_json(report, None))["aggregation"]["units"]
    assert len(units) == 2
    for unit in units:
        assert unit["n"] == 5
        assert unit["solved"] == 5
        assert len(unit["wilson95"]) == 2
        for key in ("cost_usd", "tokens", "wall_s"):
            assert set(unit[key]) == {"mean", "median", "stdev"}


def test_default_repeats_backward_compatible(tmp_path, scripted) -> None:
    scripted.script.append("Final Answer: ok")
    report = _run(
        _cfg("scripted"),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1)],
    )
    obj = json.loads(report_json(report, None))
    assert obj["settings"]["repeats"] == 1
    assert obj["results"][0]["run_id"] == "-|mock/cheap|react|t1|r0"
    assert obj["partial"] is False
    assert obj["runs_completed"] == obj["runs_planned"]
    legacy = {
        "schema_version", "generated_at", "cora_version", "settings", "total_cost_usd",
        "total_calls", "provider_cost_calls", "budget_exhausted", "rows", "results",
        "sensor_totals", "baseline", "baseline_note", "difficulty_bins", "ab", "aborted",
        "cells", "wall_s", "latency",
    }
    assert legacy <= set(obj)


def test_offline_bench_repeats(mock_config, scripted) -> None:
    scripted.script.extend(["Final Answer: ok"] * 3)
    results = asyncio.run(
        run_bench(mock_config, tasks=[BenchTask("q", "q", {}, None, "ok")], repeats=3)
    )
    table = format_table(results)
    assert "| q#2 |" in table
    assert "| q | 3/3 |" in table
    scripted.script.append("Final Answer: ok")
    single = asyncio.run(
        run_bench(mock_config, tasks=[BenchTask("q", "q", {}, None, "ok")], repeats=1)
    )
    assert "#" not in format_table(single)


def test_abort_partial_report(tmp_path, scripted) -> None:
    scripted.script.extend(["Final Answer: ok"] * 2)
    AcctV2Provider.fail_at = 3
    report = _run(
        _cfg("acct_v2", 0.0, 10.0),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1), T(2)],
        repeats=2,
    )
    assert [r.status for r in report.results] == ["solved", "solved", "error", "not_run"]
    assert report.results[2].aborted_run
    assert report.partial
    assert report.partial_reason.startswith("aborted: HTTP 402")
    assert report.runs_completed == 2
    assert report.runs_planned == 4
    obj = json.loads(report_json(report, None))
    assert sum(u["n"] for u in obj["aggregation"]["units"]) == 2


def test_cap_partial_report_runner(tmp_path, scripted) -> None:
    scripted.script.extend(["Final Answer: ok"] * 2)
    report = _run(
        _cfg("cent_v2", 0.0, 10.0),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1), T(2)],
        repeats=2,
        max_cost_usd=0.025,
        max_task_cost_usd=0.025,
    )
    assert [r.status for r in report.results] == [
        "solved", "solved", "stopped_budget", "skipped_budget",
    ]
    assert report.partial_reason == "budget cap reached (--max-cost)"
    assert report.runs_completed == 2


def test_cap_partial_report_cli(tmp_path, scripted) -> None:
    cfg = tmp_path / "cora.toml"
    cfg.write_text(
        '[[models]]\nid = "mock/cheap"\nprovider = "cent_v2"\ntier = "cheap"\n'
        "input_usd_per_mtok = 0.0\noutput_usd_per_mtok = 5.0\n"
        "\n[agent]\nreact_max_tokens = 1024\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    scripted.script.extend(["Final Answer: ok"] * 4)
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "-c", str(cfg), "-w", str(tmp_path), "--repeats", "2",
            "--tasks", "explore_find_port,explore_count_todos", "--models", "mock/cheap",
            "--protocols", "react", "--max-cost", "0.025", "--max-task-cost", "0.006",
            "--max-iterations", "1", "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.output + result.stderr
    obj = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert obj["partial"] is True
    assert obj["runs_completed"] < 4
    assert "partial: yes" in (out / "report.md").read_text(encoding="utf-8")


KILL_TOML = (
    '[[models]]\nid = "mock/cheap"\nprovider = "killer_v2"\ntier = "cheap"\n'
    "input_usd_per_mtok = 1.0\noutput_usd_per_mtok = 2.0\n"
)


def test_checkpoint_kill_and_resume(tmp_path, scripted) -> None:
    cfg = tmp_path / "cora.toml"
    cfg.write_text(KILL_TOML, encoding="utf-8")
    out = tmp_path / "out"
    args = [
        "bench", "--live", "-c", str(cfg), "-w", str(tmp_path), "--repeats", "2",
        "--tasks", "explore_find_port,explore_count_todos", "--models", "mock/cheap",
        "--protocols", "react", "--max-iterations", "1", "--max-task-cost", "0.01",
    ]
    KillerV2Provider.kill_at = 3
    result = CliRunner().invoke(app, [*args, "--out", str(out)])
    assert result.exit_code != 0
    obj = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in obj["results"]] == ["failed", "failed"]
    assert obj["partial"] is True
    assert "in progress" in obj["partial_reason"]
    prior_ids = [r["run_id"] for r in obj["results"]]

    scripted.calls.clear()
    KillerV2Provider.kill_at = None
    result = CliRunner().invoke(app, [*args, "--resume", str(out)])
    assert result.exit_code == 0, result.output + result.stderr
    assert len(scripted.calls) == 2
    obj = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert len(obj["results"]) == 4
    assert [r["run_id"] for r in obj["results"][:2]] == prior_ids
    assert obj["resumed"]["reused_runs"] == 2
    assert (out / "report.resume-backup.json").exists()


def test_atomic_write_text(tmp_path) -> None:
    target = tmp_path / "report.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")]


def test_resume_errors(tmp_path, cfg_file) -> None:
    base = [
        "bench", "--live", "-c", str(cfg_file), "-w", str(tmp_path),
        "--tasks", "explore_find_port", "--models", "mock/cheap", "--protocols", "react",
    ]
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(app, [*base, "--resume", str(empty)])
    assert result.exit_code == 2
    assert "--resume" in result.stderr

    seeded = tmp_path / "seeded"
    seeded.mkdir()
    (seeded / "report.json").write_text(
        json.dumps({"settings": {"seed": 5}, "results": []}), encoding="utf-8"
    )
    result = CliRunner().invoke(app, [*base, "--resume", str(seeded)])
    assert result.exit_code == 2
    assert "--seed" in result.stderr
