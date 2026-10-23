from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from cora.core.errors import ProviderError
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.types import CompletionRequest, Message, NativeToolCall

TOOL_PARAMS = {"type": "object", "properties": {}}
TOOLS = [{"type": "function", "function": {"name": "x", "parameters": TOOL_PARAMS}}]


def _provider(monkeypatch, handler) -> OpenRouterProvider:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")
    return OpenRouterProvider({}, transport=httpx.MockTransport(handler))


def test_body_has_tools_and_usage_include(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}}
        )

    provider = _provider(monkeypatch, handler)
    req = CompletionRequest("mock/cheap", [Message("user", "hi")], tools=TOOLS)
    asyncio.run(provider.complete(req))
    assert captured["tools"] == TOOLS
    assert captured["tool_choice"] == "auto"
    assert captured["usage"] == {"include": True}

    captured.clear()
    asyncio.run(provider.complete(CompletionRequest("mock/cheap", [Message("user", "hi")])))
    assert "tools" not in captured


def test_complete_parses_tool_calls_and_cost(monkeypatch):
    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "a",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path": "x"}'},
                        },
                        {
                            "id": "b",
                            "type": "function",
                            "function": {"name": "list_files", "arguments": "{}"},
                        },
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.00123},
    }

    provider = _provider(monkeypatch, lambda request: httpx.Response(200, json=payload))
    resp = asyncio.run(provider.complete(CompletionRequest("mock/cheap", [Message("user", "hi")])))
    assert resp.tool_calls == (
        NativeToolCall("a", "read_file", '{"path": "x"}'),
        NativeToolCall("b", "list_files", "{}"),
    )
    assert resp.text == ""
    assert resp.cost_usd == 0.00123


def test_wire_messages_tool_roles(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = _provider(monkeypatch, handler)
    messages = [
        Message("user", "go"),
        Message("assistant", "", tool_calls=(NativeToolCall("a", "list_files", "{}"),)),
        Message("tool", "out", tool_call_id="a"),
    ]
    asyncio.run(provider.complete(CompletionRequest("mock/cheap", messages, tools=TOOLS)))
    wire = captured["messages"]
    assert wire[1]["role"] == "assistant"
    assert wire[1]["content"] is None
    assert wire[1]["tool_calls"][0]["function"]["name"] == "list_files"
    assert wire[2] == {"role": "tool", "tool_call_id": "a", "content": "out"}


def test_stream_assembles_tool_call_deltas(monkeypatch):
    lines = [
        '{"choices":[{"delta":{"role":"assistant","content":null,"tool_calls":[{"index":0,"id":"call_a","type":"function","function":{"name":"read_file","arguments":""}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"pa"}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":'
        '{"arguments":"th\\": \\"a.txt\\"}"}}]}}]}',
        '{"choices":[{"delta":{"tool_calls":[{"index":1,"id":"call_b","function":{"name":"list_files","arguments":"{}"}}]}}]}',
        '{"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":7,"cost":0.0001}}',
    ]
    body_text = "".join(f"data: {line}\n\n" for line in lines) + "data: [DONE]\n\n"
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, content=body_text.encode(), headers={"content-type": "text/event-stream"}
        )

    provider = _provider(monkeypatch, handler)
    texts: list[str] = []
    resp = asyncio.run(
        provider.stream(
            CompletionRequest("mock/cheap", [Message("user", "hi")], tools=TOOLS),
            texts.append,
        )
    )
    assert resp.tool_calls == (
        NativeToolCall("call_a", "read_file", '{"path": "a.txt"}'),
        NativeToolCall("call_b", "list_files", "{}"),
    )
    assert resp.cost_usd == 0.0001
    assert texts == []
    assert "tools" in captured


def test_http_error_redacts_key(monkeypatch):
    key = "sk-or-v1-DUMMY-not-a-real-key-000"
    monkeypatch.setenv("OPENROUTER_API_KEY", key)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"echo {request.headers['authorization']}")

    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(provider.complete(CompletionRequest("mock/cheap", [Message("user", "hi")])))
    assert "DUMMY" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_transport_error_wrapped(monkeypatch):
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    provider = _provider(monkeypatch, handler)
    req = CompletionRequest("mock/cheap", [Message("user", "hi")])
    with pytest.raises(ProviderError, match="request failed"):
        asyncio.run(provider.complete(req))
    with pytest.raises(ProviderError, match="request failed"):
        asyncio.run(provider.stream(req, lambda _t: None))
