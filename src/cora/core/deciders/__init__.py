from __future__ import annotations

from dataclasses import replace
from typing import Any

from cora.core.config import CoraConfig
from cora.core.decider import Choice, Decider, accepted
from cora.core.deciders.heuristic import HeuristicDecider
from cora.core.deciders.llm import LLMDecider
from cora.core.deciders.replay import ReplayDecider, ReplayStep
from cora.core.router import HeuristicRouter, RouteDecision


def make_decider(config: CoraConfig, providers: Any) -> Decider:
    if config.decider.kind == "llm":
        return LLMDecider(config, providers)
    return HeuristicDecider(config)


def apply_tier_choice(
    decision: RouteDecision, choice: Choice, router: HeuristicRouter, min_confidence: float
) -> RouteDecision:
    if not accepted(choice, min_confidence):
        why = (choice.reason or "fallback") if choice.fallback_used else "low_confidence"
        return replace(decision, reasons=decision.reasons + (f"decider_ignored:{why}",))
    tag = f"decider:{choice.decider}:{choice.label}"
    if choice.label == decision.tier:
        return replace(decision, reasons=decision.reasons + (tag,))
    model = router.resolve(choice.label)
    if model is None:
        why_no_model = f"decider_ignored:no_{choice.label}_model"
        return replace(decision, reasons=decision.reasons + (why_no_model,))
    return RouteDecision(
        model=model,
        tier=model.tier,
        score=decision.score,
        reasons=decision.reasons + (tag,),
        grade=decision.grade,
    )


__all__ = [
    "HeuristicDecider",
    "LLMDecider",
    "ReplayDecider",
    "ReplayStep",
    "apply_tier_choice",
    "make_decider",
]
