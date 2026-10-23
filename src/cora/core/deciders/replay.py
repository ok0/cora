from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from cora.core.decider import BaseDecider, Choice, Noul, Score
from cora.core.deciders.heuristic import HeuristicDecider


@dataclass(frozen=True)
class ReplayStep:
    label: str | None = None
    value: int | None = None
    p_yes: float | None = None
    confidence: float = 1.0
    fail: str | None = None
    delay_s: float = 0.0
    cost_usd: float = 0.0


class ReplayDecider(BaseDecider):
    kind = "replay"

    def __init__(
        self,
        heuristic: HeuristicDecider,
        script: Mapping[str, Sequence[ReplayStep]],
    ) -> None:
        super().__init__()
        self.heuristic = heuristic
        self.script: dict[str, deque[ReplayStep]] = {
            q: deque(steps) for q, steps in script.items()
        }
        self.calls: list[tuple[str, str]] = []

    async def _step(self, method: str, question: str) -> ReplayStep:
        self.calls.append((method, question))
        steps = self.script.get(question)
        step = steps.popleft() if steps else ReplayStep(fail="exhausted")
        if step.delay_s > 0:
            await asyncio.sleep(step.delay_s)
        return step

    async def _fallback(
        self,
        method: str,
        question: str,
        opts: tuple[str, ...],
        lo: int,
        hi: int,
        text: str,
        features: dict,
        reason: str,
        cost: float,
    ) -> Choice | Score | Noul:
        res = await self.heuristic.answer(method, question, opts, lo, hi, text, features)
        return replace(res, fallback_used=True, reason=reason, cost_usd=cost)

    async def _choice(
        self,
        question: str,
        options: tuple[str, ...],
        text: str,
        features: dict,
        key: str,
    ) -> Choice:
        step = await self._step("choice", question)
        if step.fail:
            return await self._fallback(
                "choice", question, options, 0, 0, text, features, step.fail, step.cost_usd
            )
        label = step.label
        if label is None or label not in options:
            return await self._fallback(
                "choice", question, options, 0, 0, text, features, "schema", step.cost_usd
            )
        n = len(options)
        probs = {
            o: step.confidence if o == label else (1 - step.confidence) / (n - 1)
            for o in options
        }
        return Choice(
            label=label, probs=probs, confidence=step.confidence, cost_usd=step.cost_usd
        )

    async def _score(
        self,
        question: str,
        lo: int,
        hi: int,
        text: str,
        features: dict,
        key: str,
    ) -> Score:
        step = await self._step("score", question)
        if step.fail:
            return await self._fallback(
                "score", question, (), lo, hi, text, features, step.fail, step.cost_usd
            )
        value = step.value
        if value is None or not isinstance(value, int) or not lo <= value <= hi:
            return await self._fallback(
                "score", question, (), lo, hi, text, features, "schema", step.cost_usd
            )
        return Score(
            value=value,
            lo=lo,
            hi=hi,
            confidence=step.confidence,
            cost_usd=step.cost_usd,
        )

    async def _noul(
        self,
        question: str,
        text: str,
        features: dict,
        key: str,
    ) -> Noul:
        step = await self._step("noul", question)
        if step.fail:
            return await self._fallback(
                "noul", question, (), 0, 0, text, features, step.fail, step.cost_usd
            )
        p = step.p_yes
        if p is None or not 0 <= p <= 1:
            return await self._fallback(
                "noul", question, (), 0, 0, text, features, "schema", step.cost_usd
            )
        return Noul(p_yes=p, confidence=step.confidence, cost_usd=step.cost_usd)
