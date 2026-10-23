from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider, act
from cora.bench import e2e
from cora.bench.e2e import E2ETask, load_e2e_tasks
from cora.bench.live import run_live_bench
from cora.bench.report import report_json, report_markdown
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config
from cora.core.providers import register_provider
from e2e_util import solve_script

pytestmark = pytest.mark.slow

SAMPLE_IDS = [
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
]


@register_provider("sleepy_e2e")
class SleepyProvider(ScriptedProvider):
    async def complete(self, req):
        await asyncio.sleep(5)
        return await super().complete(req)


def _task(tid: str) -> E2ETask:
    return {t.id: t for t in load_e2e_tasks()}[tid]


def _run(config: CoraConfig, task: E2ETask, state: Path, models=("mock/cheap",), **kw):
    return asyncio.run(
        run_live_bench(
            config,
            models=list(models),
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.30,
            max_iterations=40,
            state_dir=state,
            **kw,
        )
    )


def test_success_failure_partial(scripted, mock_config, tmp_path: Path) -> None:
    todo = _task("e2e_todo_cli")

    scripted.script.extend(solve_script(todo, "reference"))
    solved = _run(mock_config, todo, tmp_path / "s1").results[0]
    assert solved.status == "solved"
    assert solved.full_pass is True
    assert solved.score == 1.0
    assert solved.end_reason == "final_answer"

    scripted.script.extend(["Final Answer: done"])
    failed = _run(mock_config, todo, tmp_path / "s2").results[0]
    assert failed.score < 1
    assert failed.full_pass is False

    scripted.script.extend(solve_script(todo, "partial"))
    partial = _run(mock_config, todo, tmp_path / "s3")
    assert 0 < partial.results[0].score < 1

    obj = json.loads(report_json(partial, None))
    assert obj["results"][0]["grader"]["checks"]
    md = report_markdown(partial, None)
    assert "### E2E tasks" in md
    assert "#### checks: e2e_todo_cli" in md
    assert "end_reason" in md


def test_iteration_and_time_limits(scripted, mock_config, tmp_path: Path) -> None:
    todo = _task("e2e_todo_cli")
    short = dataclasses.replace(todo, max_iterations=2)
    scripted.script.extend([act("list_files", {"path": "."})] * 3)
    by_iterations = _run(mock_config, short, tmp_path / "it")
    assert by_iterations.results[0].end_reason == "max_iterations"

    sleepy_config = parse_config(
        {
            "models": [
                {
                    "id": "mock/sleepy",
                    "provider": "sleepy_e2e",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )
    quick = dataclasses.replace(todo, wall_s=0.3)
    started = time.monotonic()
    report = _run(sleepy_config, quick, tmp_path / "tl", models=("mock/sleepy",))
    assert time.monotonic() - started < 5
    assert report.results[0].end_reason == "time_limit"

    assert '"end_reason": "time_limit"' in report_json(report, None)
    assert "time_limit" in report_markdown(report, None)
    assert '"end_reason": "max_iterations"' in report_json(by_iterations, None)
    assert "max_iterations" in report_markdown(by_iterations, None)


@pytest.mark.parametrize("tid", SAMPLE_IDS)
def test_workspace_has_no_reference_or_grader_during_run(
    tid: str, scripted, mock_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(tid)
    recorded: list[Path] = []
    original = e2e.prepare_workspace

    def wrapper(t: E2ETask, tmp: Path) -> Path:
        ws = original(t, tmp)
        recorded.append(ws)
        return ws

    monkeypatch.setattr(e2e, "prepare_workspace", wrapper)
    violations: list[str] = []
    entry_bytes = (task.grader_dir / task.grader_entry).read_bytes()

    def probe(_req) -> str:
        ws = recorded[-1]
        if (ws / e2e.GRADER_DIRNAME).exists():
            violations.append("grader directory present during run")
        for path in ws.rglob("*"):
            if path.is_file() and path.read_bytes() == entry_bytes:
                violations.append(f"grader entry copied: {path.name}")
        for ref in task.reference_dir.rglob("*"):
            if not ref.is_file():
                continue
            target = ws / ref.relative_to(task.reference_dir)
            if target.is_file() and target.read_bytes() == ref.read_bytes():
                violations.append(f"reference file present: {target.name}")
        return "Final Answer: done"

    scripted.script.append(probe)
    _run(mock_config, task, tmp_path / "state")
    assert recorded
    assert violations == []


def test_human_interventions(scripted, mock_config, tmp_path: Path) -> None:
    todo = _task("e2e_todo_cli")
    scripted.script.extend(["Final Answer: done"])
    default = _run(mock_config, todo, tmp_path / "d").results[0]
    assert default.human_interventions == 0

    scripted.script.extend(
        [act("edit_file", {"path": "x.txt", "old": "", "new": "x"}), "Final Answer: done"]
    )
    report = _run(mock_config, todo, tmp_path / "a", e2e_approval="ask")
    assert report.results[0].human_interventions == 1
    assert "WARNING: human_interventions > 0" in report_markdown(report, None)


def test_cli_suite_e2e_repeats3(scripted, cfg_file_gates_off: Path, tmp_path: Path) -> None:
    todo = _task("e2e_todo_cli")
    scripted.script.extend(solve_script(todo, "reference"))
    scripted.script.extend(solve_script(todo, "partial"))
    scripted.script.extend(["Final Answer: done"])
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "--suite", "e2e", "--tasks", "e2e_todo_cli", "--repeats", "3",
            "--models", "mock/cheap", "--protocols", "react", "-c", str(cfg_file_gates_off),
            "-w", str(tmp_path), "--out", str(out),
        ],
    )
    assert result.exit_code == 0, result.stderr
    obj = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert obj["settings"]["suite"] == "e2e"
    assert [r["task"] for r in obj["results"]] == ["e2e_todo_cli"] * 3
    unit = obj["aggregation"]["units"][0]
    assert unit["n"] == 3
    assert unit["solved"] == 1
    assert unit["low_n"] is True
    assert unit["score_mean"] == pytest.approx((1 + 5 / 6 + 0) / 3)
    assert obj["e2e"]["human_interventions_total"] == 0
    assert obj["e2e"]["mean_score"] is not None
    assert "WARNING: low_n" in (out / "report.md").read_text(encoding="utf-8")
