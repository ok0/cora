from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from cora.core.config import load_config, validate_openrouter_settings
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter, estimate_cost
from cora.core.providers.openrouter import OpenRouterProvider, openrouter_account_status
from cora.core.types import CompletionRequest, Message

ROOT = Path(__file__).resolve().parents[1]
CHEAP = "google/gemini-2.5-flash-lite"
req = CompletionRequest("m/x", [Message("user", "hi")])
SSE_OK = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n'


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))


def _spec():
    cfg = load_config(ROOT / "cora.toml")
    return next(m for m in cfg.models if m.id == CHEAP)


def _usage_handler(usage: dict):
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}], "usage": usage},
        )

    return handler


def test_usage_cost_preferred_over_table():
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "cost": 0.0042,
        "prompt_tokens_details": {"cached_tokens": 400},
    }
    p = OpenRouterProvider({}, transport=httpx.MockTransport(_usage_handler(usage)))
    resp = asyncio.run(p.complete(req))
    assert resp.cost_usd == 0.0042
    assert resp.cached_input_tokens == 400

    spec = _spec()
    meter = CostMeter()
    meter.record(
        spec,
        "cheap",
        "agent",
        resp.input_tokens,
        resp.output_tokens,
        cost_usd=resp.cost_usd,
        cached_input_tokens=resp.cached_input_tokens,
    )
    rec = meter.records[0]
    assert rec.cost_usd == 0.0042
    assert rec.cost_source == "provider_usage"


def test_table_fallback_without_usage_cost():
    usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 100,
        "prompt_tokens_details": {"cached_tokens": 400},
    }
    p = OpenRouterProvider({}, transport=httpx.MockTransport(_usage_handler(usage)))
    resp = asyncio.run(p.complete(req))
    assert resp.cost_usd is None
    assert resp.cached_input_tokens == 400

    spec = _spec()
    meter = CostMeter()
    meter.record(
        spec,
        "cheap",
        "agent",
        resp.input_tokens,
        resp.output_tokens,
        cost_usd=resp.cost_usd,
        cached_input_tokens=resp.cached_input_tokens,
    )
    rec = meter.records[0]
    assert rec.cost_usd == pytest.approx(estimate_cost(spec, 1000, 100, 400))
    assert rec.cost_source.startswith("catalog:")


def test_require_parameters_in_body():
    bodies: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx.Response(200, content=SSE_OK)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    def run(settings):
        bodies.clear()
        p = OpenRouterProvider(settings, transport=httpx.MockTransport(handler))
        asyncio.run(p.complete(req))
        asyncio.run(p.stream(req, lambda t: None))
        return bodies[0], bodies[1]

    c, s = run({"require_parameters": True})
    assert c["provider"] == {"require_parameters": True}
    assert s["provider"] == {"require_parameters": True}

    c, s = run({"provider_sort": "throughput", "require_parameters": True})
    assert c["provider"] == {"sort": "throughput", "require_parameters": True}
    assert s["provider"] == {"sort": "throughput", "require_parameters": True}

    c, s = run({})
    assert "provider" not in c
    assert "provider" not in s


def test_require_parameters_validation():
    with pytest.raises(ConfigError, match="require_parameters"):
        validate_openrouter_settings({"require_parameters": "yes"})
    with pytest.raises(ConfigError, match="require_parameters"):
        OpenRouterProvider({"require_parameters": 1})
    assert OpenRouterProvider({"require_parameters": True}).require_parameters is True
    assert OpenRouterProvider({"require_parameters": False}).require_parameters is False


def test_credits_403_is_info_only():
    async def get(path):
        if path == "/auth/key":
            return 200, {"data": {"limit_remaining": None}}
        return 403, {"error": {"message": "management key required"}}

    status = asyncio.run(openrouter_account_status(get))
    assert status.balance is None
    assert len(status.balance_notes) == 1
    note = status.balance_notes[0]
    assert "HTTP 403" in note
    assert "info only" in note
