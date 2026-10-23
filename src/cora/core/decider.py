from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from cora.core.metering import CostMeter

Q_TIER = "tier"
Q_GRADE = "grade"
Q_COMPLEXITY = "complexity"
Q_STUCK = "stuck"
Q_COMPLETE = "complete"


def group_question(g: str) -> str:
    return f"group:{g}"


QUESTIONS: dict[str, str] = {
    Q_TIER: "Which model tier should handle this task: cheap or strong?",
    Q_GRADE: "How hard is this request: simple, medium or complex?",
    Q_COMPLEXITY: "How complex is this task on the router's score scale?",
    Q_STUCK: "Is the agent stuck repeating the same failing step?",
    Q_COMPLETE: "Is the task complete given the final answer?",
    group_question("git"): "Does this request need git tools?",
    group_question("web"): "Does this request need web tools?",
    group_question("plan-todo"): "Does this request need planning or todo tools?",
    group_question("delegate"): "Does this request need a sub-agent delegate?",
}


@dataclass(frozen=True)
class Choice:
    label: str
    probs: dict[str, float]
    confidence: float
    fallback_used: bool = False
    decider: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class Score:
    value: int
    lo: int
    hi: int
    confidence: float
    fallback_used: bool = False
    decider: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class Noul:
    p_yes: float
    confidence: float
    fallback_used: bool = False
    decider: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    reason: str = ""

    @property
    def yes(self) -> bool:
        return self.p_yes >= 0.5


@dataclass(frozen=True)
class DecisionRecord:
    kind: str
    question: str
    input_hash: str
    output: str
    confidence: float
    cost_usd: float
    latency_ms: float
    fallback_used: bool
    decider: str
    model: str
    reason: str

    def to_event(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class DecisionHooks:
    meter: CostMeter | None = None
    call_gate: Callable[[float, float], bool] | None = None
    on_record: Callable[[DecisionRecord], None] | None = None


@runtime_checkable
class Decider(Protocol):
    kind: str
    model: str | None

    def begin_request(self, hooks: DecisionHooks) -> None: ...

    async def choice(
        self,
        question: str,
        options: Sequence[str],
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Choice: ...

    async def score(
        self,
        question: str,
        lo: int,
        hi: int,
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Score: ...

    async def noul(
        self,
        question: str,
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Noul: ...


def input_hash(
    method: str,
    question: str,
    options: Sequence[str],
    text: str,
    features: Mapping[str, Any],
) -> str:
    raw = json.dumps(
        {"m": method, "q": question, "o": list(options), "t": text, "f": dict(features)},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def accepted(result: Choice | Score | Noul, min_confidence: float) -> bool:
    return not result.fallback_used and result.confidence >= min_confidence


def _distinct_options(options: Sequence[str]) -> tuple[str, ...]:
    opts = tuple(options)
    if len(opts) < 2 or len(set(opts)) != len(opts):
        raise ValueError("options must be at least two distinct values")
    return opts


class BaseDecider:
    kind = "base"
    model: str | None = None

    def __init__(self) -> None:
        self.hooks = DecisionHooks()

    def begin_request(self, hooks: DecisionHooks) -> None:
        self.hooks = hooks

    async def choice(
        self,
        question: str,
        options: Sequence[str],
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Choice:
        opts = _distinct_options(options)
        feats = dict(features or {})
        key = input_hash("choice", question, opts, text, feats)
        t0 = time.perf_counter()
        res = await self._choice(question, opts, text, feats, key)
        res = replace(res, decider=self.kind, latency_ms=(time.perf_counter() - t0) * 1000)
        self._record("choice", question, key, res.label, res)
        return res

    async def score(
        self,
        question: str,
        lo: int,
        hi: int,
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Score:
        if not lo < hi:
            raise ValueError("score requires lo < hi")
        feats = dict(features or {})
        key = input_hash("score", question, (str(lo), str(hi)), text, feats)
        t0 = time.perf_counter()
        res = await self._score(question, lo, hi, text, feats, key)
        res = replace(res, decider=self.kind, latency_ms=(time.perf_counter() - t0) * 1000)
        self._record("score", question, key, str(res.value), res)
        return res

    async def noul(
        self,
        question: str,
        *,
        text: str = "",
        features: Mapping[str, Any] | None = None,
    ) -> Noul:
        feats = dict(features or {})
        key = input_hash("noul", question, (), text, feats)
        t0 = time.perf_counter()
        res = await self._noul(question, text, feats, key)
        res = replace(res, decider=self.kind, latency_ms=(time.perf_counter() - t0) * 1000)
        self._record("noul", question, key, f"p_yes={res.p_yes:.3f}", res)
        return res

    def _record(
        self,
        method: str,
        question: str,
        key: str,
        output: str,
        res: Choice | Score | Noul,
    ) -> None:
        rec = DecisionRecord(
            kind=method,
            question=question,
            input_hash=key,
            output=output,
            confidence=round(res.confidence, 4),
            cost_usd=res.cost_usd,
            latency_ms=round(res.latency_ms, 1),
            fallback_used=res.fallback_used,
            decider=self.kind,
            model=self.model or "-",
            reason=res.reason,
        )
        if self.hooks.on_record is not None:
            self.hooks.on_record(rec)

    async def _choice(
        self,
        question: str,
        options: tuple[str, ...],
        text: str,
        features: dict,
        key: str,
    ) -> Choice:
        raise NotImplementedError

    async def _score(
        self,
        question: str,
        lo: int,
        hi: int,
        text: str,
        features: dict,
        key: str,
    ) -> Score:
        raise NotImplementedError

    async def _noul(
        self,
        question: str,
        text: str,
        features: dict,
        key: str,
    ) -> Noul:
        raise NotImplementedError
