from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cora.bench.compare import (
    BASELINE_N1_NOTE,
    NO_BASELINE_NOTE,
    SYNTHETIC_BANNER,
    example_baseline_path,
    known_task_ids,
    load_compare_baseline,
)
from cora.cli.main import app
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]

META = """[meta]
tool = "tool"
model = "model"
date = "2026-01-01"
source = "source note"
synthetic = false
"""
TASK_OK = """[tasks.t1]
solved = true
cost_usd = 0.01
wall_s = 1.0
"""


def _result(task: str, status: str, cost: float = 0.01) -> dict:
    return {
        "task": task,
        "model": "mock/cheap",
        "protocol": "react",
        "status": status,
        "cost_usd": cost,
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_s": 1.0,
        "arm": None,
    }


def write_report(tmp: Path, results: list[dict]) -> Path:
    path = tmp / "report.json"
    path.write_text(json.dumps({"results": results, "partial": False}), encoding="utf-8")
    return path


def _baseline(tmp: Path, body: str, name: str = "baseline.toml") -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


def test_load_example_baseline() -> None:
    baseline = load_compare_baseline(example_baseline_path(), known_task_ids())
    assert baseline.meta.synthetic is True
    assert len(baseline.tasks) == 3
    assert baseline.tasks["explore_find_port"].n == 1
    assert baseline.tasks["fix_mutable_default"].solve_rate == 0.5
    assert baseline.warnings == ()


BAD_BASELINES = [
    (META.replace('tool = "tool"\n', "") + TASK_OK, "meta.tool"),
    (META.replace("synthetic = false", 'synthetic = "yes"') + TASK_OK, "meta.synthetic"),
    (META + '[tasks.t1]\nsolved = "yes"\ncost_usd = 0.01\nwall_s = 1.0\n', "tasks.t1.solved"),
    (META + '[tasks.t1]\nsolved = 1.5\ncost_usd = 0.01\nwall_s = 1.0\n', "tasks.t1.solved"),
    (META + "[tasks.t1]\nsolved = true\nwall_s = 1.0\n", "tasks.t1.cost_usd"),
    (META + "[tasks.t1]\nsolved = true\ncost_usd = 0.01\nwall_s = -1\n", "tasks.t1.wall_s"),
    (META + TASK_OK + "n = 0\n", "tasks.t1.n"),
    (META + "[tasks.t1]\nsolve = true\ncost_usd = 0.01\nwall_s = 1.0\n",
     "tasks.t1.solve is not a known field"),
    (TASK_OK, "missing [meta]"),
    ("[tasks\n", "invalid baseline file"),
]


@pytest.mark.parametrize("body, expected", BAD_BASELINES)
def test_baseline_field_errors(tmp_path: Path, body: str, expected: str) -> None:
    path = _baseline(tmp_path, body)
    with pytest.raises(ConfigError) as info:
        load_compare_baseline(path, known_task_ids())
    assert expected in str(info.value)
    assert str(tmp_path) not in str(info.value)


def test_unknown_task_id_warning(tmp_path: Path) -> None:
    body = META + TASK_OK + "[tasks.t9]\nsolved = true\ncost_usd = 0.01\nwall_s = 1.0\n"
    baseline = load_compare_baseline(_baseline(tmp_path, body), known_ids={"t1"})
    assert any("'t9'" in w for w in baseline.warnings)
    assert "t9" in baseline.tasks


def test_compare_table_and_out(tmp_path: Path) -> None:
    results = (
        [_result("t1", "solved")] * 4
        + [_result("t1", "failed")]
        + [_result("t2", "failed")] * 2
    )
    report = write_report(tmp_path, results)
    baseline = _baseline(
        tmp_path,
        META
        + "[tasks.t1]\nsolved = true\ncost_usd = 0.02\nwall_s = 5.0\n"
        + "[tasks.t3]\nsolved = false\ncost_usd = 0.01\nwall_s = 5.0\n",
    )
    out = tmp_path / "o"
    result = CliRunner().invoke(
        app, ["bench", "compare", str(report), "--baseline", str(baseline), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert (
        "| task | CORA solve | baseline solve | CORA cost | baseline cost | "
        "solved-per-dollar ratio | verdict |"
    ) in lines
    t1 = [ln for ln in lines if ln.startswith("| t1 | 4/5 | 1/1 | $0.01 | $0.02 | 1.6 |")]
    assert t1, result.stdout
    assert "insufficient data (n=5 vs 1)" in t1[0]
    assert BASELINE_N1_NOTE in t1[0]
    assert any(ln.startswith("| ALL |") for ln in lines)
    assert "unmatched: CORA only: t2 | baseline only: t3" in result.stdout
    assert SYNTHETIC_BANNER not in result.stdout
    data = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert data["configs"][0]["rows"][0]["spd_ratio"] == pytest.approx(1.6, rel=1e-6)
    assert (out / "compare.md").exists()


def test_compare_verdict_large_n(tmp_path: Path) -> None:
    report = write_report(tmp_path, [_result("t1", "solved")] * 19 + [_result("t1", "failed")])
    baseline = _baseline(
        tmp_path,
        META + "[tasks.t1]\nsolved = 0.15\ncost_usd = 0.02\nwall_s = 5.0\nn = 20\n",
    )
    result = CliRunner().invoke(
        app, ["bench", "compare", str(report), "--baseline", str(baseline)]
    )
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("| t1 |"))
    assert "CORA higher than baseline (intervals do not overlap, n=20)" in line
    assert BASELINE_N1_NOTE not in line


def test_compare_without_baseline(tmp_path: Path) -> None:
    report = write_report(tmp_path, [_result("t1", "solved"), _result("t1", "failed")])
    result = CliRunner().invoke(app, ["bench", "compare", str(report)])
    assert result.exit_code == 0, result.output
    assert NO_BASELINE_NOTE in result.stdout
    assert (
        "| task | CORA solve | Wilson 95% | CORA cost | cost per solved | solved per dollar |"
        in result.stdout
    )
    assert "baseline solve" not in result.stdout
    result = CliRunner().invoke(
        app,
        ["bench", "compare", str(report), "--baseline", str(tmp_path / "missing.toml")],
    )
    assert result.exit_code == 0, result.output
    assert "baseline file not found: missing.toml" in result.stdout
    assert NO_BASELINE_NOTE in result.stdout


def test_synthetic_banner_first_line(tmp_path: Path) -> None:
    report = write_report(tmp_path, [_result("fix_off_by_one", "solved")])
    result = CliRunner().invoke(
        app,
        ["bench", "compare", str(report), "--baseline", str(example_baseline_path())],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0] == SYNTHETIC_BANNER


def test_only_example_baseline_in_repo() -> None:
    found = []
    for sub in ("src", "tests"):
        found += list((ROOT / sub).rglob("*baseline*.toml"))
    if (ROOT / ".docs").exists():
        found += list((ROOT / ".docs").rglob("*baseline*.toml"))
    found += list(ROOT.glob("*baseline*.toml"))
    assert sorted(p.relative_to(ROOT).as_posix() for p in found) == [
        "src/cora/data/baseline.example.toml"
    ]
    text = example_baseline_path().read_text(encoding="utf-8")
    assert "SYNTHETIC / EXAMPLE" in text
    assert "synthetic = true" in text
    usage = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for block in re.findall(r"```toml\n(.*?)```", usage, re.S):
        if "[meta]" in block and "solved" in block:
            assert "synthetic = true" in block


def test_compare_invalid_inputs_exit2(tmp_path: Path) -> None:
    report = write_report(tmp_path, [_result("t1", "solved")])
    bad = _baseline(tmp_path, "[tasks\n")
    result = CliRunner().invoke(
        app, ["bench", "compare", str(report), "--baseline", str(bad)]
    )
    assert result.exit_code == 2
    result = CliRunner().invoke(app, ["bench", "compare", str(tmp_path / "nope.json")])
    assert result.exit_code == 2
    listy = tmp_path / "listy.json"
    listy.write_text(json.dumps({"results": {"a": 1}}), encoding="utf-8")
    result = CliRunner().invoke(app, ["bench", "compare", str(listy)])
    assert result.exit_code == 2
