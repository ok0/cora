from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from cora.bench.compare import CompareBaseline, load_compare_baseline
from cora.bench.stats import wilson_interval
from cora.core.errors import ConfigError
from m19_panel import (
    HARD_F,
    HARD_X,
    PanelError,
    Row,
    _fmt_interval,
    _fmt_spd,
    _spd,
    _table,
    apply_cost_basis,
    apply_error_policy,
    load_extras,
    load_rows,
)

ROOT = Path(__file__).resolve().parents[1]
TASKS = HARD_F + HARD_X
CHEAP_ARM = "a"
STRONG_ARM = "e"
EXCLUDED_ARMS = ("c_s", "d1")
DEFAULT_ARGS = "tests/fixtures/m19/panel-args.txt"
DEFAULT_EXTRAS = "tests/fixtures/m19/panel-extras.json"
DEFAULT_BASELINE = "tests/fixtures/m19/claude-code-m19.toml"

RULE_TEXT: list[str] = [
    "Oracle rule (fixed before computing): for each task, choose the arm group "
    "(cheap-only or strong) with the higher observed solve rate k/n on that task.",
    "Ties (equal k/n) go to the cheaper group: lower mean cost per trial (cost/n) "
    "on that task; if mean cost is also equal, cheap-only.",
    "Cheap-only group on a task = the best-observed arm `a` model on that task: "
    "highest k/n, then lowest mean cost per trial, then model name ascending.",
    "Strong group = arm `e` (single model). "
    "Arms c_s and d1 mix cheap and strong models and are excluded.",
    "If only one group has data for a task, that group is chosen (reason `only data`). "
    "If neither has data, the task is named as missing and left out of every denominator; "
    "nothing is imputed.",
    "Oracle totals = sum of the chosen group's k, n and cost over tasks.",
]

CAVEAT_TEXT: list[str] = [
    "This is an upper bound, not a router.",
    "It uses post-hoc knowledge of the same trials it is scored on (selection bias); "
    "the numbers are optimistic.",
    "n is small: 8 tasks, n=3 per cell; intervals are wide.",
    "No claim is made that any router can reach this bound. "
    "Nothing is adopted; routing defaults are unchanged.",
]

Tally = tuple[int, int, float]


def tally_by(rows: list[Row], arm: str) -> dict[str, dict[str, Tally]]:
    out: dict[str, dict[str, Tally]] = {}
    for row in rows:
        if row.arm != arm:
            continue
        per_model = out.setdefault(row.task, {})
        k, n, cost = per_model.get(row.model, (0, 0, 0.0))
        per_model[row.model] = (k + int(row.solved), n + 1, cost + row.cost_usd)
    return out


def best_cheap(by_model: dict[str, Tally]) -> tuple[str, Tally] | None:
    if not by_model:
        return None
    model = min(
        by_model,
        key=lambda m: (
            -Fraction(by_model[m][0], by_model[m][1]),
            by_model[m][2] / by_model[m][1],
            m,
        ),
    )
    return model, by_model[model]


def choose(cheap: Tally | None, strong: Tally | None) -> tuple[str, str]:
    if cheap is None and strong is None:
        return "none", "no data"
    if cheap is None:
        return "strong", "only data"
    if strong is None:
        return "cheap", "only data"
    kc, nc, cc = cheap
    ks, ns, cs = strong
    rate_c = Fraction(kc, nc)
    rate_s = Fraction(ks, ns)
    if rate_c > rate_s:
        return "cheap", "higher rate"
    if rate_c < rate_s:
        return "strong", "higher rate"
    if cs / ns < cc / nc:
        return "strong", "tie, cheaper"
    return "cheap", "tie, cheaper"


def oracle(
    cheap_by: dict[str, dict[str, Tally]],
    strong_by: dict[str, dict[str, Tally]],
    tasks: tuple[str, ...],
) -> dict[str, Any]:
    per_task: list[dict[str, Any]] = []
    chosen: dict[str, Tally] = {}
    missing: list[str] = []
    for task in tasks:
        best = best_cheap(cheap_by.get(task, {}))
        cheap_tally = best[1] if best else None
        cheap_model = best[0] if best else "-"
        strong_models = strong_by.get(task, {})
        if len(strong_models) > 1:
            raise PanelError(
                f"strong arm e must have one model, found {sorted(strong_models)} on {task}"
            )
        strong_tally = next(iter(strong_models.values())) if strong_models else None
        group, reason = choose(cheap_tally, strong_tally)
        per_task.append(
            {
                "task": task,
                "cheap_model": cheap_model,
                "cheap": cheap_tally,
                "strong": strong_tally,
                "choice": group,
                "reason": reason,
            }
        )
        if group == "none":
            missing.append(task)
        elif group == "cheap":
            chosen[task] = cheap_tally
        else:
            chosen[task] = strong_tally
    return {"per_task": per_task, "chosen": chosen, "missing": missing}


def best_single_cheap(
    cheap_by: dict[str, dict[str, Tally]], tasks: tuple[str, ...]
) -> tuple[str, dict[str, Tally]] | None:
    models = sorted({m for t in tasks for m in cheap_by.get(t, {})})
    best: tuple[tuple[Fraction, float, str], str, dict[str, Tally]] | None = None
    for model in models:
        per_task = {t: cheap_by[t][model] for t in tasks if model in cheap_by.get(t, {})}
        if not per_task:
            continue
        k = sum(v[0] for v in per_task.values())
        n = sum(v[1] for v in per_task.values())
        cost = sum(v[2] for v in per_task.values())
        key = (-Fraction(k, n), cost, model)
        if best is None or key < best[0]:
            best = (key, model, per_task)
    if best is None:
        return None
    return best[1], best[2]


def baseline_tallies(baseline: CompareBaseline, tasks: tuple[str, ...]) -> dict[str, Tally]:
    out: dict[str, Tally] = {}
    for task in tasks:
        if task not in baseline.tasks:
            continue
        entry = baseline.tasks[task]
        out[task] = (round(entry.solve_rate * entry.n), entry.n, entry.cost_usd * entry.n)
    return out


def summarize(
    label: str, config: str, per_task: dict[str, Tally], tasks: tuple[str, ...]
) -> dict[str, Any]:
    covered = [t for t in tasks if t in per_task]
    missing = [t for t in tasks if t not in per_task]
    k = sum(per_task[t][0] for t in covered)
    n = sum(per_task[t][1] for t in covered)
    cost = sum(per_task[t][2] for t in covered)
    return {
        "label": label,
        "config": config,
        "covered": covered,
        "missing": missing,
        "k": k,
        "n": n,
        "cost": cost,
        "ratio": k / n if n else None,
        "wilson": wilson_interval(k, n) if n else None,
        "spd": _spd(k, cost),
    }


def analyse(
    rows: list[Row], baseline: CompareBaseline, tasks: tuple[str, ...] = TASKS
) -> dict[str, Any]:
    cheap_by = tally_by(rows, CHEAP_ARM)
    strong_by = tally_by(rows, STRONG_ARM)
    orc = oracle(cheap_by, strong_by, tasks)
    single = best_single_cheap(cheap_by, tasks)
    single_model, single_tallies = single if single else ("-", {})
    strong_models = sorted({m for t in strong_by for m in strong_by[t]})
    strong_tallies = {t: next(iter(strong_by[t].values())) for t in tasks if t in strong_by}
    cheap_models = sorted({m for t in cheap_by for m in cheap_by[t]})
    excluded = sorted({r.arm for r in rows} - {CHEAP_ARM, STRONG_ARM})
    return {
        "groups": {"cheap": cheap_models, "strong": strong_models, "excluded": excluded},
        "oracle": orc,
        "rows": [
            summarize("oracle", "per-task choice", orc["chosen"], tasks),
            summarize("best single cheap", single_model, single_tallies, tasks),
            summarize(
                "strong", ", ".join(strong_models) or "-", strong_tallies, tasks
            ),
            summarize(
                "Claude Code",
                "claude-code-m19.toml (toml cost, no ledger)",
                baseline_tallies(baseline, tasks),
                tasks,
            ),
        ],
    }


def view_rows(
    specs: list[str], extras_path: str | None, policy: str, basis: str
) -> list[Row]:
    raw = [r for s in specs for r in load_rows(s)]
    if extras_path is None:
        return raw
    extras = load_extras(extras_path)
    rows, _ = apply_error_policy(raw, extras, policy)
    return apply_cost_basis(rows, extras, basis)


def _kn(tally: Tally | None) -> str:
    return "-" if tally is None else f"{tally[0]}/{tally[1]}"


def _cost(tally: Tally | None) -> str:
    return "-" if tally is None else f"{tally[2]:.4f}"


def render_view(title: str, header: list[str], result: dict[str, Any]) -> list[str]:
    groups = result["groups"]
    orc = result["oracle"]
    lines = [f"## View: {title}", *header, ""]
    lines += [
        "### Groups",
        "",
        f"- cheap-only (arm a): {', '.join(groups['cheap']) or '-'}",
        f"- strong (arm e): {', '.join(groups['strong']) or '-'}",
        f"- excluded arms: {', '.join(groups['excluded']) or '-'}",
        "",
    ]
    per_task_rows = [
        [
            p["task"],
            p["cheap_model"],
            _kn(p["cheap"]),
            _cost(p["cheap"]),
            _kn(p["strong"]),
            _cost(p["strong"]),
            p["choice"],
            p["reason"],
        ]
        for p in orc["per_task"]
    ]
    lines += [
        "### Per-task",
        "",
        *_table(
            [
                "task",
                "cheap best config",
                "cheap k/n",
                "cheap cost_usd",
                "strong k/n",
                "strong cost_usd",
                "oracle choice",
                "reason",
            ],
            per_task_rows,
        ),
        "",
    ]
    comparison_rows = []
    for s in result["rows"]:
        ratio = "n/a" if s["ratio"] is None else f"{s['ratio']:.3f}"
        wilson = "n/a" if s["wilson"] is None else _fmt_interval(s["wilson"])
        comparison_rows.append(
            [
                s["label"],
                s["config"],
                f"{len(s['covered'])}/{len(TASKS)}",
                f"{s['k']}/{s['n']}",
                ratio,
                wilson,
                f"{s['cost']:.4f}",
                _fmt_spd(s["spd"]),
                ", ".join(s["missing"]) or "none",
            ]
        )
    lines += [
        "### Comparison",
        "",
        *_table(
            [
                "row",
                "config",
                "tasks",
                "solved/total",
                "ratio",
                "wilson95",
                "cost_usd",
                "solved/$",
                "missing",
            ],
            comparison_rows,
        ),
        "",
        f"Missing oracle tasks: {', '.join(orc['missing']) or 'none'}",
        "",
    ]
    return lines


def render(
    inputs: list[str], views: list[tuple[str, list[str], dict[str, Any]]]
) -> str:
    lines = ["# M19d perfect pre-router upper bound (offline, $0)", "", "inputs:"]
    lines += [f"- {item}" for item in inputs]
    lines += ["", "## Caveats", ""]
    lines += [f"- {c}" for c in CAVEAT_TEXT]
    lines += ["", "## Oracle rule", ""]
    lines += [f"- {r}" for r in RULE_TEXT]
    lines += [""]
    for title, header, result in views:
        lines += render_view(title, header, result)
    return "\n".join(lines).rstrip("\n") + "\n"


def read_args_file(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M19d oracle upper bound over existing M19 reports "
        "(offline, no model call, no key)."
    )
    parser.add_argument("--args-file", default=DEFAULT_ARGS)
    parser.add_argument("--extras", default=DEFAULT_EXTRAS)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        if Path.cwd().resolve() != ROOT:
            raise PanelError("run from the repository root")
        specs = read_args_file(Path(args.args_file))
        baseline = load_compare_baseline(Path(args.baseline))
        billed = analyse(view_rows(specs, args.extras, "replace", "billed"), baseline)
        registered = analyse(view_rows(specs, None, "unsolved", "report"), baseline)
        text = render(
            [args.args_file, args.extras, args.baseline],
            [
                (
                    "billed",
                    [
                        "error policy: replace",
                        "cost basis: billed",
                        f"extras: {args.extras}",
                    ],
                    billed,
                ),
                (
                    "registered",
                    [
                        "error policy: unsolved",
                        "cost basis: report",
                        "extras: none",
                    ],
                    registered,
                ),
            ],
        )
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
    except (PanelError, ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
