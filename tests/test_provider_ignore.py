from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

import httpx
import pytest

from cora.core.config import parse_config, validate_openrouter_settings
from cora.core.errors import ConfigError
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
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")


req = CompletionRequest("m/x", [Message("user", "hi")], stop=["\nObservation:"])


def test_provider_ignore_in_body():
    bodies: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if body.get("stream"):
            return httpx.Response(200, content=SSE_OK)
        return httpx.Response(200, json=OK_JSON)

    def run(settings):
        bodies.clear()
        p = OpenRouterProvider(settings, transport=httpx.MockTransport(handler))
        asyncio.run(p.complete(req))
        asyncio.run(p.stream(req, lambda t: None))
        return bodies[0], bodies[1]

    c, s = run({"provider_ignore": ["amazon-bedrock"]})
    assert c["provider"] == {"ignore": ["amazon-bedrock"]}
    assert s["provider"] == {"ignore": ["amazon-bedrock"]}
    assert c["stop"] == ["\nObservation:"]
    assert s["stop"] == ["\nObservation:"]

    c, s = run(
        {"provider_sort": "throughput", "require_parameters": True, "provider_ignore": ["a", "b/c"]}
    )
    assert c["provider"] == {
        "sort": "throughput",
        "require_parameters": True,
        "ignore": ["a", "b/c"],
    }
    assert s["provider"] == {
        "sort": "throughput",
        "require_parameters": True,
        "ignore": ["a", "b/c"],
    }

    c, s = run({})
    assert "provider" not in c
    assert "provider" not in s
    assert OpenRouterProvider({}).provider_ignore == ()


BAD_VALUES = ["amazon-bedrock", [], [""], ["Amazon Bedrock"], ["a", "a"], [1]]


@pytest.mark.parametrize("bad", BAD_VALUES)
def test_provider_ignore_validation(bad):
    with pytest.raises(ConfigError, match="provider_ignore"):
        validate_openrouter_settings({"provider_ignore": bad})
    with pytest.raises(ConfigError, match="provider_ignore"):
        parse_config({"models": [MODEL], "providers": {"openrouter": {"provider_ignore": bad}}})
    with pytest.raises(ConfigError, match="provider_ignore"):
        OpenRouterProvider({"provider_ignore": bad})


def test_provider_ignore_valid_slugs_accepted():
    good = ["amazon-bedrock", "deepinfra/turbo"]
    validate_openrouter_settings({"provider_ignore": good})
    parse_config({"models": [MODEL], "providers": {"openrouter": {"provider_ignore": good}}})
    assert OpenRouterProvider({"provider_ignore": good}).provider_ignore == tuple(good)


def test_defaults_have_no_provider_ignore():
    for rel in ("cora.toml", "src/cora/data/cora.toml"):
        data = tomllib.loads((ROOT / rel).read_text(encoding="utf-8"))
        assert "provider_ignore" not in data["providers"]["openrouter"]
