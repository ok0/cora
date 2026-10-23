from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from cora.core.providers.openrouter import OpenRouterProvider, _cached_tokens
from cora.core.types import CompletionRequest, Message, NativeToolCall

SCHEMA = {
    "type": "function",
    "function": {"name": "x", "parameters": {"type": "object", "properties": {}}},
}
MARKER = [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]


def _provider(monkeypatch, handler) -> OpenRouterProvider:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")
    return OpenRouterProvider({}, transport=httpx.MockTransport(handler))


def _ok(usage: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": usage or {}},
        )

    return handler


def _conversation(cache_prefix: bool) -> CompletionRequest:
    return CompletionRequest(
        "mock/cheap",
        [
            Message("system", "SYS"),
            Message("user", "u"),
            Message(
                "assistant",
                "",
                tool_calls=(NativeToolCall("c1", "x", "{}"),),
            ),
            Message("tool", "obs", tool_call_id="c1"),
            Message("user", "u2"),
        ],
        tools=[SCHEMA],
        cache_prefix=cache_prefix,
    )


def test_marker_on_system_only(monkeypatch):
    p = _provider(monkeypatch, _ok())
    body = p._body(_conversation(True))
    assert body["messages"][0]["content"] == MARKER
    assert "cache_control" not in json.dumps(body["messages"][1:])
    assert body["tools"] == [SCHEMA]


def test_flag_off_byte_identical(monkeypatch):
    p = _provider(monkeypatch, _ok())
    off = p._body(_conversation(False))
    legacy = p._body(
        CompletionRequest(
            "mock/cheap",
            _conversation(False).messages,
            tools=[SCHEMA],
        )
    )
    assert json.dumps(off) == json.dumps(legacy)
    assert "cache_control" not in json.dumps(off)


def test_complete_sends_marker_and_no_key(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return _ok()(request)

    p = _provider(monkeypatch, handler)
    asyncio.run(p.complete(_conversation(True)))
    assert b'"cache_control"' in captured["content"]
    assert b"k-test" not in captured["content"]


def test_cached_tokens_parsed(monkeypatch):
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 5,
        "prompt_tokens_details": {"cached_tokens": 60},
    }
    p = _provider(monkeypatch, _ok(usage))
    resp = asyncio.run(p.complete(_conversation(True)))
    assert resp.cached_input_tokens == 60
    assert resp.input_tokens == 100

    p2 = _provider(monkeypatch, _ok({"prompt_tokens": 100, "completion_tokens": 5}))
    resp2 = asyncio.run(p2.complete(_conversation(True)))
    assert resp2.cached_input_tokens == 0


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({}, 0),
        ({"prompt_tokens_details": None}, 0),
        ({"prompt_tokens_details": "x"}, 0),
        ({"prompt_tokens_details": {"cached_tokens": None}}, 0),
        ({"cached_tokens": "7"}, 0),
        ({"cached_tokens": True}, 0),
        ({"cached_tokens": -3}, 0),
        ({"prompt_tokens_details": {"cached_tokens": 7.0}}, 7),
    ],
)
def test_cached_tokens_tolerant(usage, expected):
    assert _cached_tokens(usage) == expected


def test_no_system_message_untouched(monkeypatch):
    p = _provider(monkeypatch, _ok())
    msgs = [Message("user", "a"), Message("user", "b")]
    on = p._body(CompletionRequest("mock/cheap", msgs, cache_prefix=True))
    off = p._body(CompletionRequest("mock/cheap", msgs, cache_prefix=False))
    assert on == off
