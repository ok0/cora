from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cora.core.config import TIERS, CoraConfig, ModelSpec, find_model

CODE_KW_EN = re.compile(
    r"\b(fix|bug|refactor|implement|debug|traceback|exception|failing|test|tests|patch|function|class|module)\b",
    re.I,
)
CODE_KW_KO = re.compile(r"(수정|구현|버그|리팩터|디버그|테스트|함수|클래스)")
CODE_REF = re.compile(r"```|[\w./-]+\.(py|ts|js|go|rs|java|toml|json|ya?ml|md)\b")
MULTI_STEP = re.compile(r"(\n\s*\d+\.|\bthen\b|그리고|다음에)", re.I)
logger = logging.getLogger("cora.router")
PROMPT_FEATURE_KEYS: dict[str, type] = {
    "chars": int,
    "code_keywords": bool,
    "code_reference": bool,
    "multi_step": bool,
}


def prompt_features(prompt: str) -> dict[str, int | bool]:
    return {
        "chars": len(prompt),
        "code_keywords": bool(CODE_KW_EN.search(prompt) or CODE_KW_KO.search(prompt)),
        "code_reference": bool(CODE_REF.search(prompt)),
        "multi_step": bool(MULTI_STEP.search(prompt)),
    }


def score_from_features(features: Mapping[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if int(features.get("chars", 0)) >= 400:
        score += 1
        reasons.append("long_prompt")
    if features.get("code_keywords"):
        score += 1
        reasons.append("code_task_keywords")
    if features.get("code_reference"):
        score += 1
        reasons.append("code_reference")
    if features.get("multi_step"):
        score += 1
        reasons.append("multi_step")
    return score, reasons


@dataclass(frozen=True)
class RouteDecision:
    model: ModelSpec
    tier: str
    score: int
    reasons: tuple[str, ...]
    grade: str = "unknown"

    @property
    def reason_line(self) -> str:
        return ", ".join(self.reasons) if self.reasons else "no complexity signals"


class HeuristicRouter:
    def __init__(self, config: CoraConfig) -> None:
        self.config = config

    def score(self, prompt: str) -> tuple[int, list[str]]:
        return score_from_features(prompt_features(prompt))

    def grade_for_score(self, score: int) -> str:
        r = self.config.router
        if score >= r.threshold:
            return "complex"
        if score >= r.medium_threshold:
            return "medium"
        return "simple"

    def classify(self, prompt: str) -> tuple[str, int, list[str]]:
        score, reasons = self.score(prompt)
        return self.grade_for_score(score), score, reasons

    def tier_for_grade(self, grade: str) -> str:
        r = self.config.router
        target = r.default if grade == "unknown" else r.grades.get(grade, r.default)
        return self._target_model(target, []).tier

    def _target_model(self, target: str, reasons: list[str]) -> ModelSpec:
        r = self.config.router
        model = self.resolve(target)
        if model is None:
            reasons.append(
                f"no_{target}_model_configured" if target in TIERS else f"unresolved:{target}"
            )
            model = self.resolve(r.default) or next(
                (m for m in self.config.models if m.tier != target), self.config.models[0]
            )
        return model

    def resolve(self, target: str) -> ModelSpec | None:
        if target in TIERS:
            return next(
                (m for m in self.config.models if m.tier == target and m.source != "pin"),
                None,
            )
        return find_model(self.config.models, target)

    def model_for(self, target: str) -> ModelSpec:
        r = self.config.router
        for t in (r.pin, target, r.default):
            if t and self.resolve(t) is not None:
                return self.resolve(t)
        return self.config.models[0]

    def route(self, prompt: str, force_tier: str | None = None) -> RouteDecision:
        r = self.config.router
        try:
            grade, score, reasons = self.classify(prompt)
        except Exception as e:
            grade, score, reasons = "unknown", 0, [f"classifier_error:{type(e).__name__}"]
        model = self.resolve(r.pin) if r.pin else None
        if model is not None:
            reasons.append(f"pinned:{r.pin}")
        else:
            if r.pin:
                reasons.append(f"unresolved_pin:{r.pin}")
            if force_tier:
                target = force_tier
                reasons.append(f"forced:{force_tier}")
            elif r.mode == "cheap_first":
                target = "cheap"
                reasons.append("cheap_first")
            elif grade == "unknown":
                target = r.default
                reasons.append("fallback:default")
            else:
                target = r.grades.get(grade, r.default)
            model = self._target_model(target, reasons)
        logger.info(
            "route grade=%s tier=%s model=%s score=%d reasons=%s",
            grade,
            model.tier,
            model.id,
            score,
            reasons,
        )
        return RouteDecision(
            model=model,
            tier=model.tier,
            score=score,
            reasons=tuple(reasons),
            grade=grade,
        )
