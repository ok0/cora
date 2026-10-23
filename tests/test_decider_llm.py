from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from conftest import COMPLEX_PROMPT, with_decider
from cora.core.config import TIERS
from cora.core.decider import Decider, DecisionHooks
from cora.core.deciders.llm import DECIDE_MAX_TOKENS, LLMDecider
from cora.core.errors import ProviderAccountError, ProviderError
from cora.core.metering import CostMeter
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.types import CompletionRequest, CompletionResponse

pytestmark = pytest.mark.usefixtures("no_network")


def run(fn: Callable[..., Coroutine[Any, Any, None]]) -> Callable[..., None]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        asyncio.run(fn(*args, **kwargs))

    return wrapper

TEXT = COMPLEX_PROMPT
JSON_OK = '{"answer":"strong","confidence":0.9}'


class FakeProvider:
    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[CompletionRequest] = []

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.calls.append(req)
        reply = self.replies.pop(0) if self.replies else ""
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply):
            return await reply()
        if isinstance(reply, str):
            return CompletionResponse(reply, 100, 10, req.model)
        return reply


class FakePool:
    def __init__(self, get) -> None:
        self.get = get


async def slow() -> CompletionResponse:
    await asyncio.sleep(5)
    raise AssertionError("unreachable")


def make(cfg, replies: list, gate=None):
    provider = FakeProvider(replies)
    decider = LLMDecider(cfg, FakePool(lambda name: provider))
    meter = CostMeter()
    decider.begin_request(DecisionHooks(meter=meter, call_gate=gate))
    return decider, provider, meter


@pytest.fixture
def cfg(mock_config):
    return with_decider(mock_config, kind="llm")


def test_llm_decider_satisfies_protocol(cfg):
    assert isinstance(LLMDecider(cfg, FakePool(lambda name: None)), Decider)


@run
async def test_metered_gated_small_strict(cfg):
    seen: list[tuple[float, float]] = []

    def gate(spent: float, projected: float) -> bool:
        seen.append((spent, projected))
        return True

    d, provider, meter = make(cfg, [JSON_OK, '{"answer":"no","confidence":0.8}'], gate)
    res = await d.choice("tier", TIERS, text=TEXT)
    assert res.label == "strong"
    assert res.confidence == 0.9
    assert not res.fallback_used
    assert meter.records[0].purpose == "decide"
    assert len(seen) == 1
    assert seen[0][0] == 0.0 and seen[0][1] > 0
    req = provider.calls[0]
    assert req.max_tokens == DECIDE_MAX_TOKENS <= 64
    assert req.temperature == 0.0
    assert req.response_format["json_schema"]["strict"] is True
    answer_schema = req.response_format["json_schema"]["schema"]["properties"]["answer"]
    assert answer_schema["enum"] == ["cheap", "strong"]
    await d.noul("group:git", text=TEXT)
    noul_schema = provider.calls[1].response_format["json_schema"]["schema"]["properties"]
    assert noul_schema["answer"]["enum"] == ["yes", "no"]


@run
async def test_memo_once_per_request(cfg):
    d, provider, _ = make(cfg, [JSON_OK, JSON_OK, JSON_OK])
    await d.choice("tier", TIERS, text=TEXT)
    second = await d.choice("tier", TIERS, text=TEXT)
    assert len(provider.calls) == 1
    assert second.reason == "memo"
    assert second.cost_usd == 0.0
    await d.choice("tier", TIERS, text="another task")
    assert len(provider.calls) == 2
    d.begin_request(DecisionHooks(meter=CostMeter()))
    await d.choice("tier", TIERS, text=TEXT)
    assert len(provider.calls) == 3


@pytest.mark.parametrize(
    ("reply", "overrides", "gate", "reason", "calls"),
    [
        pytest.param("not json", {}, None, "bad_json", 1, id="bad_json"),
        pytest.param(
            '{"answer":"medium","confidence":0.9}', {}, None, "schema", 1, id="bad_answer"
        ),
        pytest.param(
            '{"answer":"cheap","confidence":1.5}', {}, None, "schema", 1, id="bad_confidence"
        ),
        pytest.param("", {}, None, "empty", 1, id="empty"),
        pytest.param(ProviderError("x"), {}, None, "provider_error", 1, id="provider_error"),
        pytest.param(slow, {"timeout_s": 0.05}, None, "timeout", 1, id="timeout"),
        pytest.param(JSON_OK, {}, lambda spent, projected: False, "budget", 0, id="budget"),
        pytest.param(
            JSON_OK, {"max_cost_per_decision": 1e-12}, None, "max_cost", 0, id="max_cost_projected"
        ),
        pytest.param(
            CompletionResponse(JSON_OK, 10, 5, "m", cost_usd=1.0),
            {},
            None,
            "max_cost",
            1,
            id="max_cost_actual",
        ),
    ],
)
@run
async def test_fallbacks(cfg, reply, overrides, gate, reason, calls):
    c = with_decider(cfg, **overrides)
    d, provider, _ = make(c, [reply], gate)
    res = await d.choice("tier", TIERS, text=TEXT)
    assert res.label == "strong"
    assert res.fallback_used is True
    assert res.reason == reason
    assert len(provider.calls) == calls


@run
async def test_max_cost_actual_records_meter_cost(cfg):
    reply = CompletionResponse(JSON_OK, 10, 5, "m", cost_usd=1.0)
    d, _, meter = make(cfg, [reply])
    res = await d.choice("tier", TIERS, text=TEXT)
    assert res.reason == "max_cost"
    assert meter.total_cost_usd == 1.0


@run
async def test_account_error_disables(cfg):
    d, provider, _ = make(cfg, [ProviderAccountError(402, "x")])
    first = await d.choice("tier", TIERS, text="task a")
    assert first.reason == "provider_error"
    second = await d.choice("tier", TIERS, text="task b")
    assert second.fallback_used is True
    assert second.reason == "disabled"
    assert len(provider.calls) == 1


@run
async def test_timeout_turns_off_for_request(cfg):
    c = with_decider(cfg, timeout_s=0.05)
    d, provider, _ = make(c, [slow, JSON_OK])
    first = await d.choice("tier", TIERS, text="task a")
    assert first.reason == "timeout"
    second = await d.choice("tier", TIERS, text="task b")
    assert second.reason == "disabled"
    assert len(provider.calls) == 1
    d.begin_request(DecisionHooks(meter=CostMeter()))
    third = await d.choice("tier", TIERS, text="task c")
    assert third.fallback_used is False
    assert len(provider.calls) == 2


@run
async def test_fenced_json_ok(cfg):
    reply = "```json\n{\"answer\":\"cheap\",\"confidence\":0.8}\n```"
    d, _, _ = make(cfg, [reply])
    res = await d.choice("tier", TIERS, text=TEXT)
    assert res.label == "cheap"
    assert res.fallback_used is False


def test_openrouter_body_response_format(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider = OpenRouterProvider({})
    body = provider._body(
        CompletionRequest("m", [], response_format={"type": "json_object"})
    )
    assert body["response_format"] == {"type": "json_object"}
    assert "response_format" not in provider._body(CompletionRequest("m", []))
