from __future__ import annotations

import json

import pytest

from cora.bench.aggregate import Run, aggregate, aggregation_lines
from cora.bench.stats import (
    cost_verdict,
    describe,
    fmt_pct,
    fmt_sig,
    format_n,
    solve_verdict,
    wilson_interval,
)


def _runs(costs: list[float], solved: list[bool], task: str = "t1") -> list[Run]:
    return [
        Run(arm="A", model="m", protocol="react", task=task, solved=s, cost_usd=c,
            tokens=10, wall_s=1.0)
        for c, s in zip(costs, solved, strict=True)
    ]


def test_wilson_known_values() -> None:
    lo, hi = wilson_interval(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3)
    assert hi == pytest.approx(0.9433, abs=1e-3)
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    assert wilson_interval(0, 0) is None


def test_describe_n1_stdev_null() -> None:
    assert describe([0.5])["stdev"] is None
    assert describe([1, 2, 3])["stdev"] == 1.0
    assert describe([]) == {"mean": None, "median": None, "stdev": None}


def test_bootstrap_deterministic() -> None:
    runs = _runs([0.01, 0.02, 0.03, 0.01, 0.02], [True, False, True, True, False])
    first = json.dumps(aggregate(runs), sort_keys=True)
    second = json.dumps(aggregate(runs), sort_keys=True)
    assert first == second
    assert json.loads(first)["rules"]["bootstrap_seed"] == 0


def test_unsolved_cost_per_solved_null() -> None:
    agg = aggregate(_runs([0.01, 0.01, 0.01], [False, False, False]))
    unit = agg["units"][0]
    assert unit["cost_per_solved_usd"] is None
    assert unit["cost_per_solved_ci95"] is None
    assert unit["cost_per_solved_note"] == "unsolved"


def test_solved_per_dollar_zero_cost_null() -> None:
    agg = aggregate(_runs([0.0, 0.0, 0.0], [True, False, True]))
    assert agg["units"][0]["solved_per_dollar"] is None
    assert agg["configs"][0]["solved_per_dollar"] is None
    assert agg["overall"]["solved_per_dollar"] is None


def test_solved_per_dollar_value() -> None:
    agg = aggregate(_runs([0.01, 0.02, 0.03], [True, True, False]))
    expected = 2 / 0.06
    assert agg["units"][0]["solved_per_dollar"] == pytest.approx(expected)
    assert agg["configs"][0]["solved_per_dollar"] == pytest.approx(expected)
    assert agg["overall"]["solved_per_dollar"] == pytest.approx(expected)


def test_low_n_insufficient_and_md_warning() -> None:
    runs = [
        *_runs([0.01] * 3, [True, False, True]),
        Run(arm="B", model="m", protocol="react", task="t1", solved=True, cost_usd=0.02,
            tokens=10, wall_s=1.0),
        Run(arm="B", model="m", protocol="react", task="t1", solved=False, cost_usd=0.02,
            tokens=10, wall_s=1.0),
        Run(arm="B", model="m", protocol="react", task="t1", solved=True, cost_usd=0.02,
            tokens=10, wall_s=1.0),
    ]
    agg = aggregate(runs)
    assert all(u["low_n"] for u in agg["units"])
    assert agg["verdicts"][0]["solve_rate"] == "insufficient data (n=3)"
    assert "WARNING: low_n" in "\n".join(aggregation_lines(agg))


def test_verdict_not_significant_n20() -> None:
    assert solve_verdict("A", 10, 20, "B", 12, 20) == "difference not significant (n=20)"


def test_verdict_directional_n20() -> None:
    assert solve_verdict("A", 3, 20, "B", 19, 20) == (
        "B higher than A (intervals do not overlap, n=20)"
    )


def test_cost_verdicts() -> None:
    assert cost_verdict("A", [0.01] * 20, "B", [0.02] * 20) == (
        "A cheaper than B (bootstrap 95% interval of the mean cost difference excludes 0, "
        "n=20)"
    )
    assert cost_verdict("A", [0.01] * 20, "B", [0.01] * 20) == (
        "cost difference not significant (n=20)"
    )
    assert cost_verdict("A", [0.01] * 3, "B", [0.02] * 3) == "insufficient data (n=3)"


def test_formatting() -> None:
    assert fmt_pct(1.0) == "100%"
    assert fmt_pct(0.4902) == "49%"
    assert fmt_sig(0.000779123) == "0.000779"
    assert fmt_sig(None) == "n/a"
    assert format_n(3, 5) == "n=3 vs 5"
