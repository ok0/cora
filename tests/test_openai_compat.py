from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest

from cora.bench.preflight import run_preflight, skip_line
from cora.core.config import ModelSpec
from cora.core.errors import ProviderAccountError, ProviderError
from cora.core.memory import _msg_from_dict, _msg_to_dict
from cora.core.metering import CostMeter
from cora.core.providers import account_capability, provider_events
from cora.core.providers.openai_compat import OpenAICompatProvider
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.types import CompletionRequest, Message, NativeToolCall

DUMMY_KEY = "gm-test-DUMMY-key"
FIXED_NOW = datetime(2026, 10, 15, 0, 0, 0, tzinfo=UTC)
TOOL_PARAMS = {"type": "object", "properties": {}}
TOOLS = [{"type": "function", "function": {"name": "list_files", "parameters": TOOL_PARAMS}}]
EXTRA = {"google": {"thought_signature": "sig=="}}


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


@pytest.fixture
def clk() -> Clock:
    return Clock()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def make(clk: Clock):
    def build(handler, **kw: Any) -> OpenAICompatProvider:
        settings = {
            "type": "openai_compat",
            "base_url": "https://example.test/v1",
            "api_key_env": "GEMINI_API_KEY",
            **kw,
        }
        return OpenAICompatProvider(
            settings,
            transport=httpx.MockTransport(handler),
            sleep=clk.sleep,
            clock=clk.now,
            now=lambda: FIXED_NOW,
        )

    return build


def ok(text: str = "hi", **extra: Any) -> httpx.Response:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    body.update(extra)
    return httpx.Response(200, json=body)


def sse(*chunks: dict) -> httpx.Response:
    text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(
        200, content=text.encode("utf-8"), headers={"content-type": "text/event-stream"}
    )


def complete(provider: OpenAICompatProvider, req: CompletionRequest):
    return asyncio.run(provider.complete(req))


def test_body_has_no_openrouter_fields(env, make):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["headers"] = request.headers
        captured["path"] = request.url.path
        return ok()

    req = CompletionRequest(
        "gemini-3.5-flash-lite",
        [Message("user", "hi")],
        tools=TOOLS,
        cache_prefix=True,
    )
    complete(make(handler), req)
    body = captured["body"]
    assert "usage" not in body
    assert "provider" not in body
    assert "cache_control" not in json.dumps(body)
    assert captured["headers"]["authorization"] == f"Bearer {DUMMY_KEY}"
    assert "x-title" not in captured["headers"]
    assert captured["path"].endswith("/chat/completions")


def test_unknown_fields_ignored_nonstream(env, make):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "foo": 1,
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "refusal": None,
                            "annotations": [],
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "bar": {},
                                    "function": {"name": "list_files", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
            },
        )

    req = CompletionRequest("gemini-3.5-flash-lite", [Message("user", "x")])
    resp = complete(make(handler), req)
    assert resp.tool_calls[0].name == "list_files"
    assert resp.tool_calls[0].arguments == "{}"


def test_extra_content_echoed_tool_call(env, make):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {"name": "list_files", "arguments": "{}"},
                                        "extra_content": EXTRA,
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        return ok("done")

    provider = make(handler)
    first = complete(provider, CompletionRequest("gemini-3.5-flash-lite", [Message("user", "x")]))
    messages = [
        Message("user", "x"),
        Message("assistant", "", tool_calls=first.tool_calls, extra_content=first.extra_content),
        Message("tool", "out", tool_call_id=first.tool_calls[0].id),
    ]
    complete(provider, CompletionRequest("gemini-3.5-flash-lite", messages))
    assistant = bodies[1]["messages"][1]
    assert assistant["tool_calls"][0]["extra_content"] == EXTRA


def test_extra_content_echoed_text_only(env, make):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "hello", "extra_content": EXTRA}}]},
            )
        return ok("done")

    provider = make(handler)
    first = complete(provider, CompletionRequest("gemini-3.5-flash-lite", [Message("user", "x")]))
    assert first.extra_content == EXTRA
    messages = [
        Message("user", "x"),
        Message("assistant", first.text, extra_content=first.extra_content),
        Message("user", "again"),
    ]
    complete(provider, CompletionRequest("gemini-3.5-flash-lite", messages))
    assert bodies[1]["messages"][1]["extra_content"] == EXTRA


def test_memory_roundtrip_keeps_extra_content():
    m = Message(
        "assistant",
        "",
        tool_calls=(NativeToolCall("c1", "list_files", "{}", extra_content=EXTRA),),
        extra_content={"google": {"msg": "x"}},
    )
    restored = _msg_from_dict(_msg_to_dict(m))
    assert restored == m
    assert restored.extra_content == {"google": {"msg": "x"}}
    assert restored.tool_calls[0].extra_content == EXTRA
    assert _msg_from_dict({"role": "assistant", "content": "a"}).extra_content is None


def test_stream_include_usage_and_last_usage(env, make):
    captured: dict = {}
    deltas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return sse(
            {
                "foo": 1,
                "choices": [{"delta": {"content": "Hel"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
            {"choices": [{"delta": {"content": "lo", "refusal": None}}], "usage": None},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "list_files", "arguments": "{}"},
                                    "extra_content": EXTRA,
                                }
                            ]
                        }
                    }
                ]
            },
            {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 4}},
        )

    req = CompletionRequest("gemini-3.5-flash-lite", [Message("user", "x")])
    resp = asyncio.run(make(handler).stream(req, deltas.append))
    assert captured["body"]["stream_options"] == {"include_usage": True}
    assert resp.input_tokens == 9
    assert resp.output_tokens == 4
    assert "".join(deltas) == "Hello"
    assert resp.tool_calls[0].extra_content == EXTRA


def test_missing_usage_zero_and_unpriced(env, make):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    resp = complete(
        make(handler),
        CompletionRequest("gemini-3.5-flash-lite", [Message("user", "x")]),
    )
    assert resp.input_tokens == resp.output_tokens == 0
    meter = CostMeter()
    spec = ModelSpec("gemini-3.5-flash-lite", "gemini", "cheap", None, None)
    rec = meter.record(spec, "cheap", "react", resp.input_tokens, resp.output_tokens, resp.cost_usd)
    assert rec.cost_source == "unpriced"
    free = ModelSpec("gemini-3.5-flash-lite", "gemini", "cheap", 0.0, 0.0, free_tier=True)
    rec_free = meter.record(free, "cheap", "react", 0, 0, resp.cost_usd)
    assert rec_free.cost_source == "free_tier"


def test_429_retry_after_seconds(env, make, clk):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "5"}, text="slow down")
        return ok()

    resp = complete(make(handler), CompletionRequest("m", [Message("user", "x")]))
    assert resp.text == "hi"
    assert clk.sleeps == [5.0]


def test_429_retry_after_http_date(env, make, clk):
    calls: list[int] = []
    when = format_datetime(FIXED_NOW + timedelta(seconds=3), usegmt=True)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": when}, text="slow down")
        return ok()

    complete(make(handler), CompletionRequest("m", [Message("user", "x")]))
    assert clk.sleeps == [3.0]


def test_429_backoff_without_header(env, make, clk):
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) <= 3:
            return httpx.Response(429, text="slow down")
        return ok()

    complete(make(handler), CompletionRequest("m", [Message("user", "x")]))
    assert clk.sleeps == [1, 2, 4]


def test_429_exhausted(env, make, clk):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    with pytest.raises(ProviderError, match="rate limited") as ei:
        complete(make(handler, max_429_retries=2), CompletionRequest("m", [Message("user", "x")]))
    assert not isinstance(ei.value, ProviderAccountError)
    assert clk.sleeps == [1, 2]


def test_rate_limited_events(env, make, clk):
    events: list[tuple[str, dict]] = []
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "5"}, text="slow down")
        return ok()

    with provider_events(lambda kind, data: events.append((kind, data))):
        complete(make(handler), CompletionRequest("m", [Message("user", "x")]))
    limited = [(k, d) for k, d in events if k == "rate_limited"]
    assert len(limited) == 1
    assert limited[0][1]["retry_after_s"] == 5.0
    assert limited[0][1]["retrying"] is True

    events.clear()

    def always(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    with provider_events(lambda kind, data: events.append((kind, data))):
        with pytest.raises(ProviderError):
            complete(
                make(always, max_429_retries=0), CompletionRequest("m", [Message("user", "x")])
            )
    assert events[-1][0] == "rate_limited"
    assert events[-1][1]["retrying"] is False


def test_stream_429_retry_after(env, make, clk):
    calls: list[int] = []
    deltas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "5"}, text="slow down")
        return sse({"choices": [{"delta": {"content": "hi"}}]})

    resp = asyncio.run(
        make(handler).stream(CompletionRequest("m", [Message("user", "x")]), deltas.append)
    )
    assert resp.text == "hi"
    assert clk.sleeps == [5.0]


def test_rpm_throttle_spacing(env, make, clk):
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clk.now())
        return ok()

    provider = make(handler, rpm_limit=5)

    async def run_three() -> None:
        for _ in range(3):
            await provider.complete(CompletionRequest("m", [Message("user", "x")]))

    asyncio.run(run_three())
    assert len(times) == 3
    assert all(b - a >= 12.0 for a, b in zip(times, times[1:], strict=False))


def test_no_throttle_when_unset(env, make, clk):
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clk.now())
        return ok()

    provider = make(handler)

    async def run_three() -> None:
        for _ in range(3):
            await provider.complete(CompletionRequest("m", [Message("user", "x")]))

    asyncio.run(run_three())
    assert clk.sleeps == []
    assert len(set(times)) == 1


def test_redacts_key_in_errors(env, make):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"echo {request.headers['authorization']}")

    with pytest.raises(ProviderError) as ei:
        complete(make(handler), CompletionRequest("m", [Message("user", "x")]))
    assert DUMMY_KEY not in str(ei.value)
    assert "[REDACTED]" in str(ei.value)


def test_preflight_skips_account_check_for_openai_compat(env, make):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return ok()

    provider = make(handler)
    result = asyncio.run(run_preflight({"gemini": provider}, 1.0))
    assert any(skip_line("gemini") in n for n in result.notices)
    assert seen == []
    assert account_capability(provider) is None


def test_openrouter_body_unchanged(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-DUMMY")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["headers"] = request.headers
        return ok()

    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    asyncio.run(provider.complete(CompletionRequest("mock/cheap", [Message("user", "hi")])))
    assert captured["body"]["usage"] == {"include": True}
    assert "x-title" in captured["headers"]
