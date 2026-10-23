from __future__ import annotations

import asyncio
import dataclasses
import json

import httpx
import pytest

from conftest import act
from cora.core.agent import Agent
from cora.core.errors import ProviderError
from cora.core.observability import read_events
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.react import FinalAnswerFilter
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionRequest, Message


def _run_filter(chunks: list[str]) -> str:
    f = FinalAnswerFilter()
    return "".join(f.feed(c) for c in chunks)


def test_filter_split_marker():
    assert _run_filter(["Thought: x\nFinal Ans", "wer:", "  Hel", "lo"]) == "Hello"


def test_filter_blocks_action():
    assert _run_filter(["Thought: x\nAction: read_file\n", "Final Answer: no"]) == ""


def test_filter_no_marker():
    assert _run_filter(["Thought: thinking"]) == ""


def test_openrouter_stream_parses_sse_and_usage(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    seen: dict = {}
    sse = (
        ": OPENROUTER PROCESSING\n\n"
        'data: {"choices":[{"delta":{"content":"Thought: x\\nFinal"}}],"model":"m/x"}\n\n'
        'data: {"choices":[{"delta":{"content":" Answer: hi"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    chunks: list[str] = []
    req = CompletionRequest("m/x", [Message("user", "hi")], 50, 0.0, None)
    resp = asyncio.run(provider.stream(req, chunks.append))
    assert seen["body"]["stream"] is True
    assert chunks == ["Thought: x\nFinal", " Answer: hi"]
    assert resp.text == "Thought: x\nFinal Answer: hi"
    assert (resp.input_tokens, resp.output_tokens, resp.model) == (11, 3, "m/x")


def test_openrouter_stream_http_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"nope")

    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    req = CompletionRequest("m/x", [Message("user", "hi")], 50, 0.0, None)
    with pytest.raises(ProviderError, match="HTTP 401"):
        asyncio.run(provider.stream(req, lambda _t: None))


def test_agent_streams_final_answer_and_meters(scripted, mock_config, tmp_path):
    cfg = dataclasses.replace(
        mock_config,
        models=tuple(
            dataclasses.replace(m, provider="scripted_stream") for m in mock_config.models
        ),
    )
    scripted.script[:] = [act("list_files", {}), "Thought: done\nFinal Answer: streamed hello"]
    deltas: list[str] = []
    r = asyncio.run(
        Agent(cfg, tmp_path, ApprovalPolicy("auto"), on_answer_delta=deltas.append).run("hi")
    )
    assert "".join(deltas) == "streamed hello"
    assert r.answer == "streamed hello"
    assert r.summary["calls"] == 2
    assert all(m["input_tokens"] > 0 for m in r.summary["by_model"].values())
    events = read_events(r.log_path)
    assert sum(1 for e in events if e["type"] == "llm_call") == 2
