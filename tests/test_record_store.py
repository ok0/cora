from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cora.core.providers import recording
from cora.core.providers.openai_compat import OpenAICompatProvider
from cora.core.providers.recording import (
    RecordingProvider,
    RecordStore,
    normalize_request,
    request_key,
    scrub_text,
)
from cora.core.types import CompletionRequest, CompletionResponse, Message, NativeToolCall

DUMMY_GEMINI = "gm-test-DUMMY-key"
ENTRY_KEYS = {"format", "key", "provider", "model", "recorded_at", "stream", "request", "response"}
FIXED_NOW = datetime(2026, 10, 15, tzinfo=UTC)
EXTRA = {"google": {"thought_signature": "abc"}}


def _fixed_request() -> CompletionRequest:
    return CompletionRequest(
        "mock/cheap",
        [Message("system", "be brief"), Message("user", "q")],
        tools=[{"type": "function", "function": {"name": "a", "parameters": {"x": 1, "y": 2}}}],
    )


def _key(req: CompletionRequest, workspace=None, home=None) -> str:
    return request_key(normalize_request(req, workspace=workspace, home=home))


class Fixed:
    def __init__(self, text: str, tool_calls: tuple = (), finish: str | None = "stop") -> None:
        self.text = text
        self.tool_calls = tool_calls
        self.finish = finish

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            self.text,
            3,
            1,
            req.model,
            tool_calls=self.tool_calls,
            finish_reason=self.finish,
        )


def _sse(*chunks: dict) -> httpx.Response:
    text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(
        200, content=text.encode("utf-8"), headers={"content-type": "text/event-stream"}
    )


def _gemini_provider(handler) -> OpenAICompatProvider:
    settings = {
        "type": "openai_compat",
        "base_url": "https://example.test/v1",
        "api_key_env": "GEMINI_API_KEY",
    }
    return OpenAICompatProvider(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=None,
        clock=lambda: 0.0,
        now=lambda: FIXED_NOW,
    )


def test_key_ignores_workspace_home_timestamps():
    def req(ws: str, home: str, ts: str) -> CompletionRequest:
        content = f"directory: {ws}. home {home}/x at {ts}"
        return CompletionRequest("mock/cheap", [Message("system", content)])

    a = req("/tmp/a/ws", "/Users/u1", "2026-10-15T09:30:12Z")
    b = req("/tmp/b/other", "/Users/u2", "2025-01-01 00:00")
    norm_a = normalize_request(a, workspace=Path("/tmp/a/ws"), home="/Users/u1")
    norm_b = normalize_request(b, workspace=Path("/tmp/b/other"), home="/Users/u2")
    assert request_key(norm_a) == request_key(norm_b)
    text = norm_a["messages"][0]["content"]
    assert "<WS>" in text and "<HOME>" in text and "<TS>" in text


def test_workspace_under_home_maps_to_ws():
    req = CompletionRequest("mock/cheap", [Message("system", "directory: /Users/u1/proj")])
    norm = normalize_request(req, workspace=Path("/Users/u1/proj"), home="/Users/u1")
    assert norm["messages"][0]["content"] == "directory: <WS>"


def test_key_changes_with_prompt_text():
    a = CompletionRequest("mock/cheap", [Message("user", "count to five")])
    b = CompletionRequest("mock/cheap", [Message("user", "count to six")])
    assert _key(a) != _key(b)


def test_key_stable_under_dict_order():
    a = CompletionRequest(
        "mock/cheap",
        [Message("user", "q")],
        tools=[{"type": "function", "function": {"name": "a", "parameters": {"x": 1, "y": 2}}}],
    )
    b = CompletionRequest(
        "mock/cheap",
        [Message("user", "q")],
        tools=[{"function": {"parameters": {"y": 2, "x": 1}, "name": "a"}, "type": "function"}],
    )
    assert _key(a) == _key(b)


def test_key_stable_across_processes():
    code = (
        "from cora.core.providers.recording import normalize_request, request_key\n"
        "from cora.core.types import CompletionRequest, Message\n"
        "req = CompletionRequest('mock/cheap', [Message('system', 'be brief'), "
        "Message('user', 'q')], tools=[{'type': 'function', 'function': {'name': 'a', "
        "'parameters': {'x': 1, 'y': 2}}}])\n"
        "print(request_key(normalize_request(req, workspace=None, home=None)))\n"
    )
    expected = _key(_fixed_request())
    for seed in ("0", "4242"):
        out = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        assert out.stdout.strip() == expected


def test_entry_is_deterministic_json(tmp_path):
    stub = Fixed("ok", tool_calls=(NativeToolCall("c1", "list_files", "{}", EXTRA),))
    provider = RecordingProvider(
        stub,
        name="scripted",
        store_dir=tmp_path,
        mode="record",
        now=lambda: FIXED_NOW,
    )
    req = _fixed_request()
    asyncio.run(provider.complete(req))
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    first = files[0].read_bytes()
    asyncio.run(provider.complete(req))
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 1
    second = files[0].read_bytes()
    assert first == second
    text = second.decode("utf-8")
    assert text == json.dumps(json.loads(text), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    entry = json.loads(text)
    assert set(entry) == ENTRY_KEYS
    assert entry["response"]["finish_reason"] == "stop"
    replay = RecordingProvider(None, name="scripted", store_dir=tmp_path, mode="replay")
    resp = asyncio.run(replay.complete(req))
    assert resp.finish_reason == "stop"
    assert resp.tool_calls[0].extra_content == EXTRA


def test_rerecord_replaces_entry(tmp_path):
    req = _fixed_request()
    recorder = RecordingProvider(Fixed("one"), name="scripted", store_dir=tmp_path, mode="record")
    asyncio.run(recorder.complete(req))
    recorder = RecordingProvider(Fixed("two"), name="scripted", store_dir=tmp_path, mode="record")
    asyncio.run(recorder.complete(req))
    replay = RecordingProvider(None, name="scripted", store_dir=tmp_path, mode="replay")
    assert asyncio.run(replay.complete(req)).text == "two"
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_atomic_write_no_partial(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(recording.os, "replace", boom)
    with pytest.raises(OSError):
        RecordStore(tmp_path).save({"key": "ab" + "0" * 62, "format": 1})
    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob("*.tmp")) == []


def test_scrub_text():
    secret = "sk-or-v1-DUMMY-not-a-real-key-000"
    out = scrub_text(f"k={secret} g=AIza" + "A" * 35, [secret])
    assert secret not in out
    assert "AIza" not in out
    assert "[REDACTED]" in out
    assert scrub_text("xx-abc-xx", ["abc"]) == "xx-abc-xx"


def test_openai_compat_record_has_no_key_or_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GEMINI)
    monkeypatch.setenv("CORA_TEST_ENV_MARKER", "env-marker-7f3a")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": f"echo {DUMMY_GEMINI}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    inner = _gemini_provider(handler)
    store = tmp_path / "store"
    provider = RecordingProvider(
        inner, name="gemini", store_dir=store, mode="record", secrets=[DUMMY_GEMINI]
    )
    req = CompletionRequest(
        "gemini-3.5-flash-lite", [Message("user", f"use {DUMMY_GEMINI} please")]
    )
    resp = asyncio.run(provider.complete(req))
    assert resp.finish_reason == "stop"
    texts = []
    for path in store.rglob("*"):
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8"))
    assert texts
    blob = "\n".join(texts)
    for bad in (
        DUMMY_GEMINI,
        "env-marker-7f3a",
        "authorization",
        "Authorization",
        "Bearer",
        "x-goog-api-key",
        "GEMINI_API_KEY",
    ):
        assert bad not in blob
    assert "[REDACTED]" in blob
    entry = json.loads(next(store.rglob("*.json")).read_text(encoding="utf-8"))
    assert entry["response"]["finish_reason"] == "stop"


def test_stream_finish_reason_openai_compat(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GEMINI)

    def handler(request: httpx.Request) -> httpx.Response:
        return _sse(
            {"choices": [{"delta": {"content": "hi"}}]},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    provider = _gemini_provider(handler)
    req = CompletionRequest("gemini-3.5-flash-lite", [Message("user", "hi")])
    resp = asyncio.run(provider.stream(req, lambda text: None))
    assert resp.finish_reason == "stop"
