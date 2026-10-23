from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from cora.core.config import parse_config
from cora.core.errors import ConfigError, ProviderAccountError, ProviderError
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.types import CompletionRequest, Message

MODEL = {
    "id": "m/x",
    "provider": "openrouter",
    "tier": "cheap",
    "input_usd_per_mtok": 1.0,
    "output_usd_per_mtok": 2.0,
}
OK_JSON = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
SSE_OK = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n'


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))


def endless(chunk: bytes, gap: float = 0.02):
    async def gen():
        while True:
            yield chunk
            await asyncio.sleep(gap)

    return gen()


req = CompletionRequest("m/x", [Message("user", "hi")])


@pytest.mark.slow
def test_deadline_cuts_slow_body_and_retries_within_policy():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=endless(b" "))

    p = OpenRouterProvider({"request_deadline_s": 0.2}, transport=httpx.MockTransport(handler))
    start = time.monotonic()
    with pytest.raises(ProviderError, match="RequestDeadlineExceeded") as exc:
        asyncio.run(p.complete(req))
    assert len(calls) == 3
    assert time.monotonic() - start < 10
    assert "k-test" not in str(exc.value)


def test_deadline_then_success():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, content=endless(b" "))
        return httpx.Response(200, json=OK_JSON)

    p = OpenRouterProvider({"request_deadline_s": 0.2}, transport=httpx.MockTransport(handler))
    resp = asyncio.run(p.complete(req))
    assert resp.text == "ok"
    assert len(calls) == 2


def test_defaults():
    p = OpenRouterProvider({})
    assert p.request_deadline_s == 90.0
    assert p.stream_stall_timeout_s == 30.0
    assert p.provider_sort is None


@pytest.mark.slow
def test_stream_stall_retries_then_fails():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=endless(b": OPENROUTER PROCESSING\n\n"))

    settings = {"stream_stall_timeout_s": 0.2, "request_deadline_s": 30}
    p = OpenRouterProvider(settings, transport=httpx.MockTransport(handler))
    start = time.monotonic()
    with pytest.raises(ProviderError, match="StreamStalled"):
        asyncio.run(p.stream(req, lambda t: None))
    assert len(calls) == 3
    assert time.monotonic() - start < 10


@pytest.mark.slow
def test_stream_deadline_applies_with_data_keepalive():
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=endless(b'data: {"choices":[{"delta":{}}]}\n\n'))

    settings = {"stream_stall_timeout_s": 5, "request_deadline_s": 0.3}
    p = OpenRouterProvider(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="RequestDeadlineExceeded"):
        asyncio.run(p.stream(req, lambda t: None))
    assert len(calls) == 3


def test_stream_no_retry_after_text_emitted():
    calls: list[httpx.Request] = []

    async def gen():
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        while True:
            yield b": keep-alive\n\n"
            await asyncio.sleep(0.02)

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=gen())

    chunks: list[str] = []
    p = OpenRouterProvider(
        {"stream_stall_timeout_s": 0.2}, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError, match="StreamStalled"):
        asyncio.run(p.stream(req, chunks.append))
    assert len(calls) == 1
    assert chunks == ["hi"]


def test_stream_normal_with_gaps_unaffected():
    calls: list[httpx.Request] = []

    async def gen():
        yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        await asyncio.sleep(0.05)
        yield b'data: {"choices":[{"delta":{"content":"b"}}]}\n\n'
        yield b'data: {"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n\n'
        yield b"data: [DONE]\n\n"

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=gen())

    p = OpenRouterProvider({"stream_stall_timeout_s": 1.0}, transport=httpx.MockTransport(handler))
    resp = asyncio.run(p.stream(req, lambda t: None))
    assert resp.text == "ab"
    assert len(calls) == 1


def test_provider_sort_in_body():
    bodies: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx.Response(200, content=SSE_OK)
        return httpx.Response(200, json=OK_JSON)

    p = OpenRouterProvider(
        {"provider_sort": "throughput"}, transport=httpx.MockTransport(handler)
    )
    asyncio.run(p.complete(req))
    asyncio.run(p.stream(req, lambda t: None))
    assert bodies[0]["provider"] == {"sort": "throughput"}
    assert bodies[1]["provider"] == {"sort": "throughput"}

    bodies.clear()
    p = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    asyncio.run(p.complete(req))
    asyncio.run(p.stream(req, lambda t: None))
    assert "provider" not in bodies[0]
    assert "provider" not in bodies[1]


def test_provider_settings_validation():
    with pytest.raises(ConfigError, match="provider_sort"):
        parse_config(
            {"models": [MODEL], "providers": {"openrouter": {"provider_sort": "fastest"}}}
        )
    bad_settings = (
        {"request_deadline_s": 0},
        {"stream_stall_timeout_s": True},
        {"request_deadline_s": "9"},
    )
    for bad in bad_settings:
        with pytest.raises(ConfigError):
            parse_config({"models": [MODEL], "providers": {"openrouter": bad}})
    with pytest.raises(ConfigError):
        OpenRouterProvider({"provider_sort": "x"})
    parse_config({"models": [MODEL], "providers": {"openrouter": {"provider_sort": "latency"}}})


@pytest.mark.parametrize("status", [401, 402, 403])
def test_account_statuses_raise_account_error(status):
    def handler(request):
        return httpx.Response(status, text="no")

    p = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderAccountError) as exc:
        asyncio.run(p.complete(req))
    assert exc.value.status == status
    assert isinstance(exc.value, ProviderError)
    assert f"HTTP {status}" in str(exc.value)

    with pytest.raises(ProviderAccountError) as exc:
        asyncio.run(p.stream(req, lambda t: None))
    assert exc.value.status == status


def test_stream_error_chunk_with_402_raises_account_error():
    def handler(request):
        return httpx.Response(
            200, content=b'data: {"error":{"code":402,"message":"no credits"}}\n\n'
        )

    p = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderAccountError) as exc:
        asyncio.run(p.stream(req, lambda t: None))
    assert exc.value.status == 402


def test_account_get():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path.endswith("/auth/key")
        return httpx.Response(200, json={"data": {"limit_remaining": None}})

    p = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    assert asyncio.run(p.account_get("/auth/key")) == (200, {"data": {"limit_remaining": None}})

    def boom(request):
        raise httpx.ConnectError("boom k-test")

    p = OpenRouterProvider({}, transport=httpx.MockTransport(boom))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(p.account_get("/credits"))
    assert "k-test" not in str(exc.value)
