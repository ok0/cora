from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import m15_baseline
import m15_tables as T
from cora.bench import stats
from cora.cli.main import app

pytestmark = pytest.mark.usefixtures("no_network")


def _row(status: str, **kw) -> dict:
    row = {
        "status": status,
        "budget_reason": None,
        "aborted_run": False,
        "model": "m",
        "protocol": "p",
        "task": "x",
        "cost_usd": 0.1,
        "input_tokens": 10,
        "output_tokens": 5,
        "latency_s": 1.0,
        "score": 1.0 if status == "solved" else 0.0,
        "end_reason": "final_answer",
        "check_runs": 1,
    }
    row.update(kw)
    return row


def _report_dir(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "report.json").write_text(
        json.dumps({"results": rows, "partial": False}), encoding="utf-8"
    )
    mem = d / "state" / "memory"
    mem.mkdir(parents=True)
    (mem / "s1.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"kind": "evicted"}),
                json.dumps({"kind": "evicted"}),
                json.dumps({"kind": "other"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ses = d / "state" / "sessions" / "s1"
    ses.mkdir(parents=True)
    events = [
        {"type": "parse_repaired"},
        {"type": "parse_error"},
        {"type": "parse_error"},
        {"type": "parse_error"},
        {"type": "stop"},
    ]
    (ses / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return d


def test_merge_and_derive(tmp_path: Path) -> None:
    a_rows = [_row("solved"), _row("solved"), _row("failed")]
    c_rows = [_row("solved"), _row("solved"), _row("solved")]
    a = _report_dir(tmp_path, "a", a_rows)
    c = _report_dir(tmp_path, "c", c_rows)
    merged = T.merge_reports({"A": [a], "C": [c]})
    derived = T.derive_routed(merged, {"x": "cheap"})
    labels = {r["arm"] for r in derived["results"]}
    assert labels == {"A cheap", "C strong", "auto-routed (derived)"}
    d_rows = [r for r in derived["results"] if r.get("derived")]
    assert len(d_rows) == 3
    for d_row, a_row in zip(d_rows, a_rows, strict=True):
        stripped = {k: v for k, v in d_row.items() if k not in ("arm", "derived")}
        assert stripped == {k: v for k, v in a_row.items()}
    strong = T.derive_routed(merged, {"x": "strong"})
    strong_rows = [r for r in strong["results"] if r.get("derived")]
    assert len(strong_rows) == 3
    for d_row, c_row in zip(strong_rows, c_rows, strict=True):
        stripped = {k: v for k, v in d_row.items() if k not in ("arm", "derived")}
        assert stripped == c_row


def test_cells_completed_status_and_stop_reasons(tmp_path: Path) -> None:
    rows = [
        _row("solved"),
        _row("solved"),
        _row("stopped_budget", budget_reason="total", end_reason="budget_total"),
    ]
    a = _report_dir(tmp_path, "a", rows)
    merged = T.merge_reports({"A": [a]})
    cs = {(c.arm, c.task): c for c in T.cells(merged)}
    cell = cs[("A cheap", "x")]
    assert cell.n == 2
    assert cell.k == 2
    assert cell.stop_reasons.get("budget_total") == 1


def test_gate_not_reached_tag(tmp_path: Path) -> None:
    b = _report_dir(
        tmp_path,
        "b",
        [_row("failed", check_runs=0, end_reason="cost_limit")],
    )
    merged = T.merge_reports({"B": [b]})
    cell = T.cells(merged)[0]
    assert cell.stop_reasons == {"cost_limit+gate not reached": 1}


def _cell(arm: str, k: int, n: int) -> T.Cell:
    return T.Cell(
        arm=arm,
        task="x",
        k=k,
        n=n,
        wilson=stats.wilson_interval(k, n) if k <= n else None,
        total_cost=0.0,
        mean_cost=None,
        solved_per_dollar=None,
        stop_reasons={},
        check_runs=(),
    )


@pytest.mark.parametrize(
    ("a", "c", "expected"),
    [
        ((3, 3), (3, 3), "saturated"),
        ((0, 3), (3, 3), "inconclusive"),
        ((2, 3), (3, 3), "inconclusive"),
        ((0, 10), (10, 10), "gap"),
        ((3, 2), (3, 3), "blocked"),
        (None, (3, 3), "blocked"),
    ],
)
def test_saturation_rule(
    a: tuple[int, int] | None, c: tuple[int, int] | None, expected: str
) -> None:
    a_cell = _cell("A cheap", *a) if a is not None else None
    c_cell = _cell("C strong", *c) if c is not None else None
    assert T.saturation(a_cell, c_cell) == expected


def test_log_counts(tmp_path: Path) -> None:
    d = _report_dir(tmp_path, "r", [_row("solved")])
    assert T.log_counts(d) == {"evicted": 2, "parse_repaired": 1, "parse_error": 3}
    assert T.log_counts(tmp_path / "empty") == {
        "evicted": 0,
        "parse_repaired": 0,
        "parse_error": 0,
    }


def test_merged_report_accepted_by_bench_compare(tmp_path: Path) -> None:
    task = "query_client_timeout"
    a = _report_dir(tmp_path, "a", [_row("solved", task=task), _row("failed", task=task)])
    c = _report_dir(tmp_path, "c", [_row("solved", task=task), _row("solved", task=task)])
    out = tmp_path / "m15"
    rc = T.main(["--arm", f"A={a}", "--arm", f"C={c}", "--out", str(out)])
    assert rc == 0
    result = CliRunner().invoke(
        app,
        ["bench", "compare", str(out / "report.json"), "--out", str(tmp_path / "cmp")],
    )
    assert result.exit_code == 0, result.output
    text = result.stdout
    for path in (tmp_path / "cmp").rglob("*"):
        if path.is_file():
            text += path.read_text(encoding="utf-8", errors="ignore")
    assert "A cheap" in text
    assert "auto-routed (derived)" in text


def test_routes_cover_11_tasks() -> None:
    assert set(T.M12_ROUTES) == set(m15_baseline.TASK_IDS)
    assert set(T.M12_ROUTES.values()) <= {"cheap", "strong"}
