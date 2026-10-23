from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import act
from cora.bench.live import run_live_bench
from cora.bench.live_tasks import PYTEST_CHECK, LiveTask
from cora.bench.report import report_json, report_markdown
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config
from cora.core.errors import ConfigError

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
NO_CHECK = LiveTask(
    id="auto_none",
    kind="bugfix",
    prompt="Fix rng.py.",
    files={"rng.py": RNG_BUG},
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
def test_auto_source_uses_detected_check(tmp_path, scripted):
    scripted.script[:] = [
        act("read_file", {"path": "test_hidden.py"}),
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
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T],
        sensor=True,
        sensor_source="auto",
    )
    res = report.results[0]
    assert res.status == "solved"
    assert res.check_runs == 2
    for call in scripted.calls:
        for msg in call.messages:
            assert "HIDDEN_GRADER_MARKER" not in str(msg.content)
    assert report.settings["sensor"]["source"] == "auto"
    assert report.settings["sensor"]["no_check_tasks"] == []
    assert "source=auto" in report_markdown(report, None)


@pytest.mark.slow
def test_auto_source_no_detectable_check(tmp_path, scripted):
    scripted.script[:] = ["Final Answer: done"]
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[NO_CHECK],
        sensor=True,
        sensor_source="auto",
    )
    res = report.results[0]
    assert res.check_runs == 0
    assert res.status != "error"
    assert report.settings["sensor"]["no_check_tasks"] == [NO_CHECK.id]


@pytest.mark.slow
def test_oracle_default_settings_unchanged(tmp_path, scripted):
    scripted.script[:] = ["Final Answer: done"] * 6
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T],
        sensor=True,
    )
    assert "source" not in report.settings["sensor"]
    data = json.loads(report_json(report, None))
    assert "source" not in data["settings"]["sensor"]


def test_invalid_sensor_source(tmp_path):
    with pytest.raises(ConfigError):
        run(
            fixed_config(),
            tmp_path,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[T],
            sensor=True,
            sensor_source="x",
        )


def test_cli_sensor_source_requires_live_sensor():
    r = CliRunner().invoke(app, ["bench", "--sensor-source", "auto"])
    assert r.exit_code == 2
    assert "requires --live --sensor" in r.output


def test_cli_sensor_source_rejects_bad_value():
    r = CliRunner().invoke(app, ["bench", "--sensor-source", "bad"])
    assert r.exit_code == 2
