from __future__ import annotations

import signal as _signal
from collections.abc import Sequence
from pathlib import Path

from cora.core.agent import RunResult
from cora.core.budget import BudgetGovernor
from cora.core.metering import CostMeter
from cora.core.state import Session, StopReason

OUTCOME_KEYS = (
    "ok",
    "stop_reason",
    "final_answer",
    "session_id",
    "iterations",
    "cost_usd",
    "tokens",
    "wall_s",
    "models",
    "profile",
    "tools",
    "policy",
    "budget",
    "warnings",
    "errors",
    "exit_code",
)
BUDGET_STOPS = frozenset({"cost_limit", "max_iterations", "budget_exceeded"})


def policy_denials(summary: dict, extra: int = 0) -> int:
    pol = summary.get("policy") or {}
    return int(pol.get("deny", 0)) + int(pol.get("ask_resolved_deny", 0)) + extra


def metered_totals(meter: CostMeter | None) -> tuple[float, list[str]]:
    if meter is None:
        return 0.0, []
    return float(meter.total_cost_usd), list(meter.summary().get("by_model", {}))


def session_totals(session: Session | None) -> tuple[float, list[str]]:
    if session is None:
        return 0.0, []
    return metered_totals(CostMeter.from_list(session.meter))


def outcome_stop_reason(
    r: RunResult,
    *,
    tripped: str | None = None,
    denials: int = 0,
    signal: int | None = None,
) -> str:
    raw = str(r.stop_reason)
    if signal is not None or raw == "interrupted":
        return "interrupted"
    if raw in BUDGET_STOPS or tripped:
        return "budget_exceeded"
    if raw == "final_answer":
        return "final_answer"
    if policy_denials(r.summary, denials) > 0:
        return "policy_blocked"
    return raw


def exit_code(stop_reason: str, *, signal: int | None = None) -> int:
    if stop_reason == "interrupted":
        return 143 if signal == _signal.SIGTERM else 130
    if stop_reason == "final_answer":
        return 0
    if stop_reason == "budget_exceeded":
        return 4
    if stop_reason == "policy_blocked":
        return 5
    return 1


def outcome_dict(
    r: RunResult,
    governor: BudgetGovernor | None,
    *,
    wall_s: float,
    warnings: Sequence[str] = (),
    errors: Sequence[str] = (),
    denials: int = 0,
    signal: int | None = None,
) -> dict:
    stop_reason = outcome_stop_reason(
        r,
        tripped=governor.tripped if governor else None,
        denials=denials,
        signal=signal,
    )
    by_model = r.summary.get("by_model", {})
    cached = sum(int(m.get("cached_input_tokens", 0)) for m in by_model.values())
    tokens = {
        "in": sum(int(m.get("input_tokens", 0)) for m in by_model.values()),
        "out": sum(int(m.get("output_tokens", 0)) for m in by_model.values()),
    }
    if cached > 0:
        tokens["cached"] = cached
    return {
        "ok": stop_reason == "final_answer",
        "stop_reason": stop_reason,
        "final_answer": r.answer,
        "session_id": r.session.id,
        "iterations": governor.usage().iterations if governor else r.session.total_iterations,
        "cost_usd": float(r.summary.get("total_cost_usd", 0.0)),
        "tokens": tokens,
        "wall_s": round(wall_s, 3),
        "models": list(by_model),
        "profile": [
            {
                "model": g["model"],
                "provider": g["provider"],
                "calls": g["calls"],
                "input_tokens": g["input_tokens"],
                "output_tokens": g["output_tokens"],
                "cached_input_tokens": g.get("cached_input_tokens", 0),
                "cost_usd": g["cost_usd"] if g.get("price_known", True) else None,
                "cost_source": g["cost_source"],
                "p50_latency_s": g.get("p50_latency_s"),
                "excluded_from_cost_usd": bool(g.get("self_hosted")),
            }
            for g in (r.summary.get("by_model_provider") or {}).values()
        ],
        "tools": dict(governor.tool_counts) if governor else {},
        "policy": r.summary.get("policy"),
        "budget": governor.to_dict() if governor else None,
        "warnings": list(warnings),
        "errors": list(errors),
        "exit_code": exit_code(stop_reason, signal=signal),
    }


def error_outcome(
    message: str,
    code: int = 2,
    *,
    session_id: str | None = None,
    warnings: Sequence[str] = (),
    wall_s: float = 0.0,
    stop_reason: str = "error",
    cost_usd: float = 0.0,
    models: Sequence[str] = (),
) -> dict:
    return {
        "ok": False,
        "stop_reason": stop_reason,
        "final_answer": None,
        "session_id": session_id,
        "iterations": 0,
        "cost_usd": float(cost_usd),
        "tokens": {"in": 0, "out": 0},
        "wall_s": round(wall_s, 3),
        "models": list(models),
        "profile": [],
        "tools": {},
        "policy": None,
        "budget": None,
        "warnings": list(warnings),
        "errors": [message],
        "exit_code": code,
    }


def interrupted_result(session: Session, log_path: Path) -> RunResult:
    return RunResult(
        session,
        None,
        StopReason.INTERRUPTED,
        CostMeter.from_list(session.meter).summary(session.delegation_stats),
        log_path,
    )
