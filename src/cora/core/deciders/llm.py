from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from cora.core.config import CoraConfig
from cora.core.decider import QUESTIONS, BaseDecider, Choice, DecisionHooks, Noul, Score
from cora.core.deciders.heuristic import HeuristicDecider
from cora.core.errors import ProviderAccountError
from cora.core.metering import estimate_cost, projected_cost
from cora.core.router import HeuristicRouter
from cora.core.types import CompletionRequest, Message, messages_tokens

DECIDE_MAX_TOKENS = 48
MAX_INPUT_CHARS = 2000
SYSTEM = (
    "You are a fast classifier inside a coding agent. Answer with JSON only: "
    "{\"answer\": <one allowed value>, \"confidence\": <number 0..1>}. No other text."
)


def response_format(answer_schema: dict) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "decision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "answer": answer_schema,
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["answer", "confidence"],
                "additionalProperties": False,
            },
        },
    }


def build_messages(
    question: str,
    allowed: Sequence[str],
    text: str,
    features: Mapping[str, Any],
) -> list[Message]:
    lines = [
        f"Question: {QUESTIONS.get(question, question)}",
        f"Allowed answers: {', '.join(allowed)}",
    ]
    if features:
        lines.append(f"Features: {json.dumps(features, sort_keys=True, default=str)}")
    if text:
        lines.append(f"Input:\n{text[:MAX_INPUT_CHARS]}")
    return [Message("system", SYSTEM), Message("user", "\n".join(lines))]


class _Fallback(Exception):
    def __init__(self, reason: str, cost: float) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cost = cost


def _valid_answer(answer: Any, schema: dict) -> bool:
    enum = schema["enum"]
    if schema["type"] == "integer":
        return isinstance(answer, int) and not isinstance(answer, bool) and answer in enum
    return isinstance(answer, str) and answer in enum


class LLMDecider(BaseDecider):
    kind = "llm"

    def __init__(
        self,
        config: CoraConfig,
        providers: Any,
        *,
        heuristic: HeuristicDecider | None = None,
    ) -> None:
        super().__init__()
        self.settings = config.decider
        self.agent_cap = config.agent.max_cost_usd
        self.providers = providers
        self.heuristic = heuristic if heuristic is not None else HeuristicDecider(config)
        r = HeuristicRouter(config)
        self.spec = r.resolve(self.settings.model) or r.resolve("cheap") or config.models[0]
        self.model = self.spec.id
        self._memo: dict[str, Any] = {}
        self._request_off: str | None = None
        self._disabled: str | None = None

    def begin_request(self, hooks: DecisionHooks) -> None:
        super().begin_request(hooks)
        self._memo.clear()
        self._request_off = None

    async def _ask(
        self,
        question: str,
        allowed: Sequence[str],
        answer_schema: dict,
        text: str,
        features: Mapping[str, Any],
    ) -> tuple[Any, float, float]:
        if self._disabled or self._request_off:
            raise _Fallback("disabled", 0)
        msgs = build_messages(question, allowed, text, features)
        projected = projected_cost(self.spec, messages_tokens(msgs), DECIDE_MAX_TOKENS)
        if projected > self.settings.max_cost_per_decision:
            raise _Fallback("max_cost", 0)
        hooks = self.hooks
        spent = hooks.meter.total_cost_usd if hooks.meter else 0.0
        if spent + projected > self.agent_cap or (
            hooks.call_gate is not None and not hooks.call_gate(spent, projected)
        ):
            raise _Fallback("budget", 0)
        req = CompletionRequest(
            self.spec.id,
            msgs,
            DECIDE_MAX_TOKENS,
            0.0,
            None,
            None,
            response_format(answer_schema),
        )
        t0 = time.monotonic()
        try:
            async with asyncio.timeout(self.settings.timeout_s):
                resp = await self.providers.get(self.spec.provider).complete(req)
        except TimeoutError:
            self._request_off = "timeout"
            raise _Fallback("timeout", 0) from None
        except ProviderAccountError:
            self._disabled = "account"
            raise _Fallback("provider_error", 0) from None
        except Exception:
            raise _Fallback("provider_error", 0) from None
        latency = time.monotonic() - t0
        if hooks.meter is not None:
            cost = hooks.meter.record(
                self.spec,
                self.spec.tier,
                "decide",
                resp.input_tokens,
                resp.output_tokens,
                cost_usd=resp.cost_usd,
                cached_input_tokens=resp.cached_input_tokens,
                latency_s=latency,
            ).cost_usd
        elif resp.cost_usd is not None:
            cost = resp.cost_usd
        else:
            cost = estimate_cost(self.spec, resp.input_tokens, resp.output_tokens)
        if cost > self.settings.max_cost_per_decision:
            raise _Fallback("max_cost", cost)
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.text.strip(), flags=re.I)
        if not t:
            raise _Fallback("empty", cost)
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            raise _Fallback("bad_json", cost) from None
        if not isinstance(data, dict):
            raise _Fallback("schema", cost)
        answer = data.get("answer")
        conf = data.get("confidence")
        if (
            not _valid_answer(answer, answer_schema)
            or isinstance(conf, bool)
            or not isinstance(conf, (int, float))
            or not 0 <= conf <= 1
        ):
            raise _Fallback("schema", cost)
        return answer, float(conf), cost

    async def _resolve(
        self,
        method: str,
        question: str,
        opts: tuple[str, ...],
        lo: int,
        hi: int,
        text: str,
        features: dict,
        key: str,
        allowed: list[str],
        answer_schema: dict,
        build: Any,
    ) -> Choice | Score | Noul:
        if key in self._memo:
            cached = self._memo[key]
            return replace(
                cached,
                cost_usd=0.0,
                reason=cached.reason if cached.fallback_used else "memo",
            )
        try:
            answer, conf, cost = await self._ask(question, allowed, answer_schema, text, features)
        except _Fallback as f:
            res: Choice | Score | Noul = await self.heuristic.answer(
                method, question, opts, lo, hi, text, features
            )
            res = replace(res, fallback_used=True, reason=f.reason, cost_usd=f.cost)
        else:
            res = build(answer, conf, cost)
        self._memo[key] = res
        return res

    async def _choice(
        self,
        question: str,
        options: tuple[str, ...],
        text: str,
        features: dict,
        key: str,
    ) -> Choice:
        def build(answer: str, conf: float, cost: float) -> Choice:
            n = len(options)
            probs = {
                o: conf if o == answer else (1 - conf) / (n - 1) for o in options
            }
            return Choice(label=answer, probs=probs, confidence=conf, cost_usd=cost)

        return await self._resolve(
            "choice",
            question,
            options,
            0,
            0,
            text,
            features,
            key,
            list(options),
            {"type": "string", "enum": list(options)},
            build,
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
        def build(answer: int, conf: float, cost: float) -> Score:
            return Score(value=answer, lo=lo, hi=hi, confidence=conf, cost_usd=cost)

        return await self._resolve(
            "score",
            question,
            (),
            lo,
            hi,
            text,
            features,
            key,
            [str(i) for i in range(lo, hi + 1)],
            {"type": "integer", "enum": list(range(lo, hi + 1))},
            build,
        )

    async def _noul(
        self,
        question: str,
        text: str,
        features: dict,
        key: str,
    ) -> Noul:
        def build(answer: str, conf: float, cost: float) -> Noul:
            p_yes = conf if answer == "yes" else 1 - conf
            return Noul(p_yes=p_yes, confidence=conf, cost_usd=cost)

        return await self._resolve(
            "noul",
            question,
            (),
            0,
            0,
            text,
            features,
            key,
            ["yes", "no"],
            {"type": "string", "enum": ["yes", "no"]},
            build,
        )
