from __future__ import annotations

import itertools
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cora.bench.stats import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    LOW_N,
    bootstrap_ratio_ci,
    cost_verdict,
    describe,
    fmt_interval_pct,
    fmt_pct,
    fmt_sig,
    solve_verdict,
    wilson_interval,
)


@dataclass(frozen=True)
class Run:
    arm: str | None
    model: str
    protocol: str
    task: str
    solved: bool
    cost_usd: float
    tokens: int
    wall_s: float
    score: float | None = None


RULES = {
    "wilson_z": 1.96,
    "bootstrap_iterations": 2000,
    "bootstrap_seed": 0,
    "bootstrap_method": "percentile",
    "interval": 0.95,
    "low_n_threshold": 5,
    "solved": "status == solved (e2e: full_pass)",
    "independence_note": (
        "intervals assume independent runs; repeats of one task may not be independent"
    ),
}

AGG_HEADING = (
    "### Repeats and aggregation (Wilson 95% for solve rate; bootstrap 95% (2000 resamples, "
    "seed 0) for cost per solved; low_n when n < 5)"
)


def config_label(arm: str | None, model: str, protocol: str) -> str:
    return arm or f"{model} {protocol}"


def _solved_per_dollar(solved: int, total_cost: float) -> float | None:
    return solved / total_cost if total_cost > 0 else None


def _score_mean(runs: Sequence[Run]) -> float | None:
    scores = [r.score for r in runs if r.score is not None]
    return statistics.fmean(scores) if scores else None


def unit_stats(runs: Sequence[Run], *, seed: int, iterations: int) -> dict:
    first = runs[0]
    n = len(runs)
    solved = sum(1 for r in runs if r.solved)
    costs = [r.cost_usd for r in runs]
    total_cost = sum(costs, 0.0)
    cps_ci = (
        bootstrap_ratio_ci(
            costs,
            [1.0 if r.solved else 0.0 for r in runs],
            iterations=iterations,
            seed=seed,
        )
        if solved
        else None
    )
    wilson = wilson_interval(solved, n)
    return {
        "arm": first.arm,
        "model": first.model,
        "protocol": first.protocol,
        "task": first.task,
        "config": config_label(first.arm, first.model, first.protocol),
        "n": n,
        "solved": solved,
        "solve_rate": solved / n,
        "wilson95": list(wilson) if wilson is not None else None,
        "low_n": n < LOW_N,
        "cost_usd": describe(costs),
        "tokens": describe([float(r.tokens) for r in runs]),
        "wall_s": describe([r.wall_s for r in runs]),
        "total_cost_usd": total_cost,
        "cost_per_solved_usd": total_cost / solved if solved else None,
        "cost_per_solved_ci95": list(cps_ci) if cps_ci is not None else None,
        "cost_per_solved_note": "unsolved" if solved == 0 else None,
        "solved_per_dollar": _solved_per_dollar(solved, total_cost),
        "score_mean": _score_mean(runs),
    }


def _config_row(label: str, runs: Sequence[Run]) -> dict:
    n = len(runs)
    solved = sum(1 for r in runs if r.solved)
    total_cost = sum((r.cost_usd for r in runs), 0.0)
    wilson = wilson_interval(solved, n)
    return {
        "config": label,
        "n": n,
        "solved": solved,
        "solve_rate": solved / n,
        "wilson95": list(wilson) if wilson is not None else None,
        "low_n": n < LOW_N,
        "total_cost_usd": total_cost,
        "cost_per_solved_usd": total_cost / solved if solved else None,
        "solved_per_dollar": _solved_per_dollar(solved, total_cost),
        "mean_cost_usd": statistics.fmean([r.cost_usd for r in runs]),
        "score_mean": _score_mean(runs),
    }


def aggregate(
    runs: Sequence[Run], *, seed: int = BOOTSTRAP_SEED, iterations: int = BOOTSTRAP_ITERATIONS
) -> dict:
    unit_groups: dict[tuple[str | None, str, str, str], list[Run]] = {}
    config_groups: dict[str, list[Run]] = {}
    for r in runs:
        unit_groups.setdefault((r.arm, r.model, r.protocol, r.task), []).append(r)
        config_groups.setdefault(config_label(r.arm, r.model, r.protocol), []).append(r)
    units = [unit_stats(rs, seed=seed, iterations=iterations) for rs in unit_groups.values()]
    configs = [_config_row(label, rs) for label, rs in config_groups.items()]
    total_cost = sum((r.cost_usd for r in runs), 0.0)
    overall = {
        "n": len(runs),
        "solved": sum(1 for r in runs if r.solved),
        "total_cost_usd": total_cost,
        "solved_per_dollar": _solved_per_dollar(
            sum(1 for r in runs if r.solved), total_cost
        ),
        "score_mean": _score_mean(runs),
    }
    verdicts: list[dict[str, Any]] = []
    for a, b in itertools.combinations(configs, 2):
        verdicts.append(
            {
                "a": a["config"],
                "b": b["config"],
                "n_a": a["n"],
                "n_b": b["n"],
                "solve_rate": solve_verdict(
                    a["config"], a["solved"], a["n"], b["config"], b["solved"], b["n"]
                ),
                "cost": cost_verdict(
                    a["config"],
                    [r.cost_usd for r in config_groups[a["config"]]],
                    b["config"],
                    [r.cost_usd for r in config_groups[b["config"]]],
                    iterations=iterations,
                    seed=seed,
                ),
            }
        )
    return {
        "rules": RULES,
        "units": units,
        "configs": configs,
        "overall": overall,
        "verdicts": verdicts,
    }


def _cost_per_solved_cell(unit: dict) -> str:
    if unit["cost_per_solved_note"] is not None:
        return unit["cost_per_solved_note"]
    text = fmt_sig(unit["cost_per_solved_usd"])
    ci = unit["cost_per_solved_ci95"]
    if ci is not None:
        text += f" ({fmt_sig(ci[0])}-{fmt_sig(ci[1])})"
    return text


def aggregation_lines(agg: dict) -> list[str]:
    lines = [
        AGG_HEADING,
        "",
        "| task | config | solved | solve_rate | wilson95 | cost_mean_usd | cost_median_usd | "
        "cost_stdev_usd | tokens_mean | wall_mean_s | cost_per_solved_usd (95% CI) | "
        "solved_per_dollar | score_mean | flags |",
        "|" + "---|" * 14,
    ]
    low_units = 0
    for u in agg["units"]:
        flags = "low_n" if u["low_n"] else "-"
        low_units += 1 if u["low_n"] else 0
        lines.append(
            f"| {u['task']} | {u['config']} | {u['solved']}/{u['n']} | "
            f"{fmt_pct(u['solve_rate'])} | {fmt_interval_pct(u['wilson95'])} | "
            f"{fmt_sig(u['cost_usd']['mean'])} | {fmt_sig(u['cost_usd']['median'])} | "
            f"{fmt_sig(u['cost_usd']['stdev'])} | {fmt_sig(u['tokens']['mean'])} | "
            f"{fmt_sig(u['wall_s']['mean'])} | {_cost_per_solved_cell(u)} | "
            f"{fmt_sig(u['solved_per_dollar'])} | {fmt_sig(u['score_mean'])} | {flags} |"
        )
    if low_units:
        lines += [
            "",
            f"WARNING: low_n - {low_units} unit(s) have fewer than {LOW_N} runs; intervals are "
            'wide and comparisons report "insufficient data".',
        ]
    lines += [
        "",
        "#### By config",
        "",
        "| config | solved | solve_rate | wilson95 | total_cost_usd | solved_per_dollar | "
        "score_mean | flags |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in agg["configs"]:
        flags = "low_n" if c["low_n"] else "-"
        lines.append(
            f"| {c['config']} | {c['solved']}/{c['n']} | {fmt_pct(c['solve_rate'])} | "
            f"{fmt_interval_pct(c['wilson95'])} | {fmt_sig(c['total_cost_usd'])} | "
            f"{fmt_sig(c['solved_per_dollar'])} | {fmt_sig(c['score_mean'])} | {flags} |"
        )
    lines += ["", "#### Verdicts"]
    if agg["verdicts"]:
        for v in agg["verdicts"]:
            lines.append(
                f"- {v['a']} vs {v['b']}: solve rate: {v['solve_rate']}; cost: {v['cost']}"
            )
    else:
        lines.append("- (only one config: no comparison)")
    lines += ["", f"note: {RULES['independence_note']}"]
    return lines
