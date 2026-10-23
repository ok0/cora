from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cora.bench.e2e import select_e2e_tasks
from cora.cli.main import app
from e2e_util import solve_script


def _base(cfg: Path, tmp: Path, out: Path, *extra: str) -> list[str]:
    return [
        "bench", "--live", "--suite", "e2e", "--models", "mock/cheap", "--protocols", "react",
        "-c", str(cfg), "-w", str(tmp), "--out", str(out), *extra,
    ]


def _report(out: Path) -> dict:
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_e2e_unknown_task_exits_2(scripted, cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, _base(cfg_file, tmp_path, tmp_path / "out", "--tasks", "nope"))
    assert result.exit_code == 2
    assert "unknown e2e task id" in result.stderr


def test_e2e_tasks_filter_and_repeats(scripted, cfg_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app, _base(cfg_file, tmp_path, out, "--tasks", "e2e_text_stats", "--repeats", "2")
    )
    assert result.exit_code == 0, result.stderr
    obj = _report(out)
    assert obj["settings"]["tasks"] == ["e2e_text_stats"]
    assert [r["repeat_index"] for r in obj["results"]] == [0, 1]


def test_e2e_task_cost_override_plan(cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench", "plan", "--suite", "e2e", "--tasks", "e2e_todo_cli", "--models", "mock/strong",
            "--protocols", "react", "--max-cost", "0.30", "--e2e-task-cost", "0.12",
            "-c", str(cfg_file),
        ],
    )
    assert result.exit_code == 0, result.stderr
    row = next(line for line in result.stdout.splitlines() if "e2e_todo_cli" in line)
    assert "| 0.120000 |" in row


def test_e2e_no_override_keeps_task_toml(cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench", "plan", "--suite", "e2e", "--tasks", "e2e_todo_cli", "--models", "mock/strong",
            "--protocols", "react", "--max-cost", "0.30", "-c", str(cfg_file),
        ],
    )
    assert result.exit_code == 0, result.stderr
    row = next(line for line in result.stdout.splitlines() if "e2e_todo_cli" in line)
    assert "| 0.030000 |" in row


def test_e2e_task_cost_override_live(scripted, cfg_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        _base(
            cfg_file, tmp_path, out,
            "--tasks", "e2e_todo_cli", "--max-cost", "0.30", "--e2e-task-cost", "0.12",
        ),
    )
    assert result.exit_code == 0, result.stderr
    settings = _report(out)["settings"]
    assert settings["e2e"]["tasks"][0]["cost_usd"] == 0.12
    assert settings["max_task_cost_usd"] == 0.12


def test_e2e_task_cost_above_max_cost_exits_2(scripted, cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        _base(
            cfg_file, tmp_path, tmp_path / "out",
            "--tasks", "e2e_todo_cli", "--max-cost", "0.10", "--e2e-task-cost", "0.20",
        ),
    )
    assert result.exit_code == 2
    assert "--e2e-task-cost" in result.stderr


def test_e2e_task_cost_default_suite_exits_2(scripted, cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "bench", "--live", "--models", "mock/cheap", "--protocols", "react",
            "--tasks", "fix_off_by_one", "--e2e-task-cost", "0.05",
            "-c", str(cfg_file), "-w", str(tmp_path), "--out", str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 2
    assert "--e2e-task-cost" in result.stderr


def test_e2e_task_cost_requires_live(cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["bench", "--e2e-task-cost", "0.1", "-c", str(cfg_file)])
    assert result.exit_code == 2
    assert "require --live" in result.stderr


def test_e2e_sensor_oracle_rejected(scripted, cfg_file: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, _base(cfg_file, tmp_path, tmp_path / "out", "--tasks", "e2e_text_stats", "--sensor")
    )
    assert result.exit_code == 2
    assert "--sensor-source auto" in result.stderr


def test_e2e_sensor_auto_detected(scripted, no_network, cfg_file: Path, tmp_path: Path) -> None:
    text_stats = select_e2e_tasks(["e2e_text_stats"])[0]
    scripted.script.extend(solve_script(text_stats, "reference"))
    scripted.script.extend(["Final Answer: done"])
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        _base(
            cfg_file, tmp_path, out,
            "--tasks", "e2e_text_stats,e2e_todo_cli", "--sensor", "--sensor-source", "auto",
        ),
    )
    assert result.exit_code == 0, result.stderr
    obj = _report(out)
    sensor = obj["settings"]["sensor"]
    assert sensor["enabled"] is True
    assert sensor["source"] == "auto"
    assert sensor["no_check_tasks"] == ["e2e_todo_cli"]
    by_task = {r["task"]: r for r in obj["results"]}
    assert by_task["e2e_text_stats"]["check_runs"] >= 1
    assert by_task["e2e_todo_cli"]["check_runs"] == 0
    for r in obj["results"]:
        assert ".cora_grader" not in (r.get("detail") or "")


def test_e2e_without_sensor_unchanged(scripted, cfg_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app, _base(cfg_file, tmp_path, out, "--tasks", "e2e_text_stats")
    )
    assert result.exit_code == 0, result.stderr
    obj = _report(out)
    assert obj["settings"]["sensor"]["enabled"] is False
    assert "source" not in obj["settings"]["sensor"]
    assert obj["results"][0]["check_runs"] == 0
