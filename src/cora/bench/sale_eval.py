from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cora.core.errors import ConfigError
from cora.core.router import prompt_features, score_from_features
from cora.core.sale import (
    PLACEHOLDER_WARNING,
    HeuristicBidGenerator,
    PlanFeatures,
    TierTable,
    choose_tier,
    plan_features_from_text,
)

POLICIES = ("always-cheap", "always-strong", "heuristic-router", "sale-lite")
CASE_KEYS = frozenset({"id", "task", "plan", "plan_text", "outcomes", "note"})
OUTCOME_KEYS = frozenset({"success", "cost"})


@dataclass(frozen=True)
class Outcome:
    success: bool
    cost: float


@dataclass(frozen=True)
class SaleCase:
    id: str
    task: str
    features: PlanFeatures
    outcomes: dict[str, Outcome]


@dataclass(frozen=True)
class PolicyRow:
    policy: str
    total_cost: float
    mean_cost: float
    solve_rate: float
    strong_share: float
    over_budget: int
    recorded: int


@dataclass(frozen=True)
class SaleEvalReport:
    cases: int
    tiers: tuple[str, ...]
    tier_source: str
    placeholder: bool
    unit: str
    reward: float
    budget_cap: float
    router_threshold: int
    rows: tuple[PolicyRow, ...]
    case_rows: tuple[dict, ...]


class _BadLine(ValueError):
    pass


def _parse_outcomes(raw: Any, table: TierTable) -> dict[str, Outcome]:
    if not isinstance(raw, dict):
        raise _BadLine("'outcomes' must be an object")
    out: dict[str, Outcome] = {}
    for tier, o in raw.items():
        if tier not in table.names:
            raise _BadLine(
                f"unknown tier {tier!r} in 'outcomes'; expected one of {list(table.names)}"
            )
        if not isinstance(o, dict) or set(o) != OUTCOME_KEYS:
            raise _BadLine(f"outcomes.{tier} needs exactly 'success' and 'cost'")
        s = o["success"]
        if not isinstance(s, bool):
            raise _BadLine(f"outcomes.{tier}.success must be true or false")
        c = o["cost"]
        if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or c < 0:
            raise _BadLine(f"outcomes.{tier}.cost must be a number >= 0")
        out[tier] = Outcome(s, float(c))
    return out


def _parse_case(line: str, table: TierTable) -> SaleCase:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise _BadLine(f"invalid JSON ({e.msg})") from e
    if not isinstance(data, dict):
        raise _BadLine("each line must be a JSON object")
    unknown = sorted(set(data) - CASE_KEYS)
    if unknown:
        raise _BadLine(f"unknown keys {unknown}")
    cid = data.get("id")
    if not isinstance(cid, str) or not cid:
        raise _BadLine("missing required field 'id' (non-empty string)")
    task = data.get("task", "")
    if not isinstance(task, str):
        raise _BadLine("'task' must be a string")
    for key in ("note", "plan_text"):
        if key in data and not isinstance(data[key], str):
            raise _BadLine(f"'{key}' must be a string")
    if "plan" in data:
        try:
            features = PlanFeatures.from_mapping(data["plan"])
        except ValueError as e:
            raise _BadLine(f"invalid 'plan': {e}") from e
    elif "plan_text" in data:
        features = plan_features_from_text(data["plan_text"])
    else:
        raise _BadLine("missing required field 'plan' or 'plan_text'")
    outcomes = _parse_outcomes(data["outcomes"], table) if "outcomes" in data else {}
    return SaleCase(cid, task, features, outcomes)


def load_sale_cases(path: Path, table: TierTable) -> list[SaleCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"cannot read cases file {path}: {e}") from e
    cases: list[SaleCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            case = _parse_case(line, table)
            if case.id in seen:
                raise _BadLine(f"duplicate id {case.id!r}")
        except _BadLine as e:
            raise ConfigError(f"{path}:{lineno}: {e}") from e
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise ConfigError(f"{path}: no cases (file is empty)")
    return cases


def heuristic_router_tier(task: str, table: TierTable, threshold: int) -> str:
    score, _ = score_from_features(prompt_features(task))
    return table.tiers[-1].name if score >= threshold else table.tiers[0].name


def run_sale_eval(
    cases: Sequence[SaleCase],
    table: TierTable,
    *,
    reward: float,
    budget_cap: float,
    router_threshold: int,
) -> SaleEvalReport:
    if not cases:
        raise ValueError("no cases")
    gen = HeuristicBidGenerator(reward)
    strong = table.tiers[-1].name
    acc = {
        p: {"cost": 0.0, "success": 0.0, "strong": 0, "over": 0, "recorded": 0} for p in POLICIES
    }
    case_rows: list[dict] = []
    for c in cases:
        bids = gen.bids(c.task, table, c.features)
        by_tier = {b.tier: b for b in bids}
        decision = choose_tier(bids, budget_cap)
        choices = {
            "always-cheap": table.tiers[0].name,
            "always-strong": strong,
            "heuristic-router": heuristic_router_tier(c.task, table, router_threshold),
            "sale-lite": decision.tier,
        }
        for policy, tier in choices.items():
            a = acc[policy]
            bid = by_tier[tier]
            rec = c.outcomes.get(tier)
            if rec is not None:
                a["cost"] += rec.cost
                a["success"] += 1.0 if rec.success else 0.0
                a["recorded"] += 1
            else:
                a["cost"] += bid.estimated_cost
                a["success"] += bid.expected_success
            a["strong"] += int(tier == strong)
            a["over"] += int(bid.estimated_cost > budget_cap)
        case_rows.append(
            {
                "id": c.id,
                "features": asdict(c.features),
                "choices": choices,
                "sale_over_budget": decision.over_budget,
                "bids": [
                    {
                        "tier": b.tier,
                        "estimated_cost": round(b.estimated_cost, 6),
                        "expected_success": round(b.expected_success, 6),
                        "value": round(b.value, 6),
                    }
                    for b in bids
                ],
            }
        )
    n = len(cases)
    rows = tuple(
        PolicyRow(
            p,
            acc[p]["cost"],
            acc[p]["cost"] / n,
            acc[p]["success"] / n,
            acc[p]["strong"] / n,
            acc[p]["over"],
            acc[p]["recorded"],
        )
        for p in POLICIES
    )
    return SaleEvalReport(
        cases=n,
        tiers=table.names,
        tier_source=table.source,
        placeholder=table.placeholder,
        unit=table.unit,
        reward=reward,
        budget_cap=budget_cap,
        router_threshold=router_threshold,
        rows=rows,
        case_rows=tuple(case_rows),
    )


def format_sale_eval(r: SaleEvalReport) -> str:
    lines: list[str] = []
    if r.placeholder:
        lines.append(PLACEHOLDER_WARNING)
    lines.append(
        f"sale eval: cases={r.cases} tiers={','.join(r.tiers)} bids=heuristic "
        f"reward={r.reward:g} budget_cap={r.budget_cap:g}"
    )
    lines.append(f"tier table: {r.tier_source} (unit: {r.unit})")
    lines.append(
        f"{'policy':<17} {'total_cost':>11} {'mean_cost':>10} {'solve_rate':>10} "
        f"{'strong_share':>12} {'over_budget':>11} {'recorded':>8}"
    )
    for p in r.rows:
        lines.append(
            f"{p.policy:<17} {p.total_cost:>11.4f} {p.mean_cost:>10.4f} {p.solve_rate:>10.4f} "
            f"{p.strong_share:>12.4f} {p.over_budget:>11d} {p.recorded:>8d}"
        )
    lines.append(
        "expected values from the tier table and plan features; "
        "recorded outcomes replace them (recorded column)"
    )
    if r.placeholder:
        lines.append(PLACEHOLDER_WARNING)
    return "\n".join(lines)


def sale_eval_json(r: SaleEvalReport) -> str:
    payload: dict[str, Any] = {
        "warning": PLACEHOLDER_WARNING if r.placeholder else None,
        "placeholder": r.placeholder,
        "tier_source": r.tier_source,
        "unit": r.unit,
        "tiers": list(r.tiers),
        "bids": "heuristic",
        "reward": r.reward,
        "budget_cap": r.budget_cap,
        "router_threshold": r.router_threshold,
        "cases": r.cases,
        "policies": [
            {k: round(v, 6) if isinstance(v, float) else v for k, v in asdict(row).items()}
            for row in r.rows
        ],
        "rows": list(r.case_rows),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
