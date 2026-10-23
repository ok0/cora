from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

from cora.bench.e2e import E2ETask
from cora.bench.live_tasks import LiveTask
from cora.core.config import CoraConfig, ModelSpec
from cora.core.router import HeuristicRouter

ASSUMED_INPUT_TOKENS_PER_CALL = 16_000
# planning assumption (typical output per call), not the request cap
ASSUMED_OUTPUT_TOKENS_PER_CALL = 1024
PLAN_NOTE = (
    "upper bounds are conservative estimates, not a guarantee: each iteration is assumed to "
    "use 16000 input and 1024 output tokens at the cora.toml price, capped by the per-task "
    "cost limit"
)
BUDGET_REMINDER = (
    "reminder: the live budget is set per milestone against the project hard cap in the "
    "charter; this command does not track what was already spent"
)
UnitKey = tuple[str | None, str, str, str]


@dataclass(frozen=True)
class PlanCell:
    arm: str | None
    model: str
    protocol: str
    task: str
    repeats: int
    completed: int
    max_iterations: int
    task_cap_usd: float
    per_run_usd: float | None
    prior_mean_usd: float | None
    unknown_models: tuple[str, ...]

    @property
    def estimate(self) -> float | None:
        return self.prior_mean_usd if self.prior_mean_usd is not None else self.per_run_usd

    @property
    def remaining(self) -> int:
        return max(0, self.repeats - self.completed)

    @property
    def subtotal_usd(self) -> float | None:
        if self.estimate is None:
            return None
        return self.estimate * self.remaining

    def subtotal_at(self, r: int) -> float | None:
        if self.estimate is None:
            return None
        return self.estimate * max(0, r - self.completed)


@dataclass(frozen=True)
class BudgetPlan:
    cells: tuple[PlanCell, ...]
    max_cost_usd: float
    repeats: int

    @property
    def runs(self) -> int:
        return sum(c.remaining for c in self.cells)

    @property
    def total_usd(self) -> float | None:
        subtotals = [c.subtotal_usd for c in self.cells]
        if any(s is None for s in subtotals):
            return None
        return sum(subtotals)

    @property
    def exceeds(self) -> bool:
        total = self.total_usd
        return total is not None and total > self.max_cost_usd + 1e-12

    def total_at(self, r: int) -> float | None:
        subtotals = [c.subtotal_at(r) for c in self.cells]
        if any(s is None for s in subtotals):
            return None
        return sum(subtotals)

    def suggest_repeats(self) -> int | None:
        if self.total_usd is None:
            return None
        for r in range(self.repeats, -1, -1):
            total = self.total_at(r)
            if total is not None and total <= self.max_cost_usd + 1e-12:
                return r
        return 0

    @property
    def unknown_models(self) -> tuple[str, ...]:
        return tuple(sorted({m for c in self.cells for m in c.unknown_models}))

    def to_dict(self) -> dict:
        return {
            "repeats": self.repeats,
            "max_cost_usd": self.max_cost_usd,
            "runs": self.runs,
            "total_max_usd": self.total_usd,
            "exceeds": self.exceeds,
            "suggested_repeats": self.suggest_repeats(),
            "unknown_models": list(self.unknown_models),
            "assumptions": {
                "input_tokens_per_call": ASSUMED_INPUT_TOKENS_PER_CALL,
                "output_tokens_per_call": ASSUMED_OUTPUT_TOKENS_PER_CALL,
                "note": PLAN_NOTE,
            },
            "cells": [asdict(c) | {"subtotal_usd": c.subtotal_usd} for c in self.cells],
        }


def per_call_usd(spec: ModelSpec) -> float:
    return (
        ASSUMED_INPUT_TOKENS_PER_CALL * spec.input_usd_per_mtok
        + ASSUMED_OUTPUT_TOKENS_PER_CALL * spec.output_usd_per_mtok
    ) / 1e6


def per_run_upper_usd(
    specs: Sequence[ModelSpec | None],
    max_iterations: int,
    task_cap_usd: float,
    extra_usd: float = 0.0,
) -> float | None:
    if any(s is None or not s.price_known for s in specs):
        return None
    priced = [s for s in specs if s is not None]
    return min(
        task_cap_usd,
        max_iterations * max(per_call_usd(s) for s in priced) + extra_usd,
    )


def task_limits(
    task: LiveTask | E2ETask, max_iterations: int, max_task_cost_usd: float
) -> tuple[int, float]:
    if isinstance(task, E2ETask):
        return min(max_iterations, task.max_iterations), min(max_task_cost_usd, task.cost_usd)
    return max_iterations, max_task_cost_usd


def _spec_by_id(config: CoraConfig, model_id: str) -> ModelSpec | None:
    return next((m for m in config.models if m.id == model_id), None)


def _unknown(pairs: Sequence[tuple[str, ModelSpec | None]]) -> tuple[str, ...]:
    return tuple(i for i, s in pairs if s is None or not s.price_known)


def build_plan(
    config: CoraConfig,
    *,
    tasks: Sequence[LiveTask],
    models: Sequence[str],
    protocols: Sequence[str],
    arms: Sequence[str] | None,
    max_iterations: int,
    max_task_cost_usd: float,
    max_cost_usd: float,
    repeats: int,
    prior: Mapping[UnitKey, Sequence[float]] | None = None,
) -> BudgetPlan:
    prior_map = prior or {}
    cells: list[PlanCell] = []

    def add(
        arm: str | None,
        label: str,
        protocol: str,
        task: LiveTask,
        priced: Sequence[tuple[str, ModelSpec | None]],
        extra_usd: float,
    ) -> None:
        iters, cap = task_limits(task, max_iterations, max_task_cost_usd)
        prior_costs = prior_map.get((arm, label, protocol, task.id), [])
        cells.append(
            PlanCell(
                arm=arm,
                model=label,
                protocol=protocol,
                task=task.id,
                repeats=repeats,
                completed=len(prior_costs),
                max_iterations=iters,
                task_cap_usd=cap,
                per_run_usd=per_run_upper_usd(
                    [s for _, s in priced], iters, cap, extra_usd
                ),
                prior_mean_usd=statistics.fmean(prior_costs) if prior_costs else None,
                unknown_models=_unknown(priced),
            )
        )

    if arms is None:
        for task in tasks:
            for model_id in dict.fromkeys(models):
                for protocol in dict.fromkeys(protocols):
                    spec = _spec_by_id(config, model_id)
                    add(None, model_id, protocol, task, [(model_id, spec)], 0.0)
        return BudgetPlan(tuple(cells), max_cost_usd, repeats)

    cheap = _spec_by_id(config, models[0])
    strong = HeuristicRouter(config).resolve("strong")
    strong_label = strong.id if strong is not None else "strong"
    protocol = protocols[0]
    for task in tasks:
        for arm in arms:
            extra = config.delegation.max_total_cost_usd if arm.startswith("deleg-on") else 0.0
            if arm == "strong-only":
                add(arm, strong_label, protocol, task, [(strong_label, strong)], extra)
            elif arm == "auto-routed":
                add(
                    arm,
                    "auto",
                    protocol,
                    task,
                    [(models[0], cheap), (strong_label, strong)],
                    extra,
                )
            else:
                add(arm, models[0], protocol, task, [(models[0], cheap)], extra)
    return BudgetPlan(tuple(cells), max_cost_usd, repeats)


def _money(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.6f}"


def plan_markdown(plan: BudgetPlan, title_suffix: str = "") -> str:
    lines = [
        f"## CORA bench plan (no calls made){title_suffix}",
        "",
        f"repeats: {plan.repeats} | max_cost_usd: {plan.max_cost_usd:g} | runs: {plan.runs}",
        "",
        "| arm | model | protocol | task | repeats | max_iterations | task_cap_usd | "
        "per_run_max_usd | subtotal_usd |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in plan.cells:
        lines.append(
            f"| {c.arm or '-'} | {c.model} | {c.protocol} | {c.task} | {c.repeats} | "
            f"{c.max_iterations} | {c.task_cap_usd:.6f} | {_money(c.per_run_usd)} | "
            f"{_money(c.subtotal_usd)} |"
        )
    total = plan.total_usd
    lines.append(
        f"| TOTAL | | | | {plan.runs} runs | | | | {_money(total)} |"
    )
    lines.append("")
    if total is not None:
        lines.append(f"total_max_usd: {total:.6f}")
    else:
        unknown = ", ".join(plan.unknown_models)
        lines.append(
            f"total_max_usd: unbounded/unknown (no price in cora.toml for: {unknown})"
        )
    if plan.exceeds and total is not None:
        lines.append(
            f"OVER CAP (초과): estimated maximum ${total:.6f} > --max-cost "
            f"${plan.max_cost_usd:g}; bench --live refuses to start, or trims repeats with "
            "--trim-to-budget (bench는 거부되거나 trim됨)"
        )
        r = plan.suggest_repeats()
        if r is not None and r >= 1:
            lines.append(f"suggested --repeats: {r}")
        else:
            lines.append(
                "suggested --repeats: none (even one repeat exceeds the cap; lower "
                "--max-iterations or --max-task-cost, or select fewer tasks)"
            )
    lines += ["", PLAN_NOTE, BUDGET_REMINDER]
    return "\n".join(lines) + "\n"
