from __future__ import annotations

from dataclasses import replace

from cora.core.config import CoraConfig
from cora.core.decider import (
    Q_COMPLETE,
    Q_COMPLEXITY,
    Q_GRADE,
    Q_STUCK,
    Q_TIER,
    BaseDecider,
    Choice,
    Noul,
    Score,
)
from cora.core.router import HeuristicRouter, score_from_features
from cora.core.toolgroups import request_signals


def _one_hot(options: tuple[str, ...], label: str) -> dict[str, float]:
    return {o: 1.0 if o == label else 0.0 for o in options}


class HeuristicDecider(BaseDecider):
    kind = "heuristic"

    def __init__(self, config: CoraConfig) -> None:
        super().__init__()
        self.router = HeuristicRouter(
            replace(config, router=replace(config.router, pin=None))
        )

    async def _choice(
        self,
        question: str,
        options: tuple[str, ...],
        text: str,
        features: dict,
        key: str,
    ) -> Choice:
        if question == Q_TIER:
            if text:
                label = self.router.route(text).tier
            else:
                grade = self.router.grade_for_score(score_from_features(features)[0])
                label = self.router.tier_for_grade(grade)
        elif question == Q_GRADE:
            if text:
                label = self.router.route(text).grade
            else:
                label = self.router.grade_for_score(score_from_features(features)[0])
        else:
            return Choice(
                label=options[0],
                probs=_one_hot(options, options[0]),
                confidence=0.0,
                reason="unknown_question",
            )
        if label not in options:
            return Choice(
                label=options[0],
                probs=_one_hot(options, options[0]),
                confidence=0.0,
                reason="label_not_in_options",
            )
        return Choice(label=label, probs=_one_hot(options, label), confidence=1.0)

    async def _score(
        self,
        question: str,
        lo: int,
        hi: int,
        text: str,
        features: dict,
        key: str,
    ) -> Score:
        if question == Q_COMPLEXITY:
            value = self.router.score(text)[0] if text else score_from_features(features)[0]
            return Score(value=min(hi, max(lo, value)), lo=lo, hi=hi, confidence=1.0)
        return Score(value=lo, lo=lo, hi=hi, confidence=0.0, reason="unknown_question")

    async def _noul(
        self,
        question: str,
        text: str,
        features: dict,
        key: str,
    ) -> Noul:
        if question.startswith("group:"):
            g = question.removeprefix("group:")
            signals = request_signals(text, plan_mode=bool(features.get("plan_mode")))
            p = 1.0 if g in signals else 0.0
        elif question == Q_STUCK:
            thr = int(features.get("threshold", 3)) or 3
            p = min(1.0, int(features.get("streak", 0)) / thr)
        elif question == Q_COMPLETE:
            p = 1.0 if features.get("has_answer") else 0.0
        else:
            return Noul(p_yes=0.0, confidence=0.0, reason="unknown_question")
        return Noul(p_yes=p, confidence=max(p, 1 - p))

    async def answer(
        self,
        method: str,
        question: str,
        opts: tuple[str, ...],
        lo: int,
        hi: int,
        text: str,
        features: dict,
    ) -> Choice | Score | Noul:
        if method == "choice":
            return await self._choice(question, opts, text, features, "")
        if method == "score":
            return await self._score(question, lo, hi, text, features, "")
        return await self._noul(question, text, features, "")
