from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from cora.core.config import find_config, load_config, parse_config
from cora.core.errors import ConfigError, MissingAPIKeyError
from cora.core.providers import create_provider
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.router import HeuristicRouter
from cora.core.types import CompletionRequest, Message


def _config(cheap_id: str):
    return parse_config(
        {
            "models": [
                {
                    "id": cheap_id,
                    "provider": "openrouter",
                    "tier": "cheap",
                    "input_usd_per_mtok": 0.2,
                    "output_usd_per_mtok": 0.8,
                },
                {
                    "id": "b/strong",
                    "provider": "openrouter",
                    "tier": "strong",
                    "input_usd_per_mtok": 0.6,
                    "output_usd_per_mtok": 2.5,
                },
            ]
        }
    )


def test_model_swap_changes_selected_model():
    assert HeuristicRouter(_config("a/cheap")).route("What is 2+2?").model.id == "a/cheap"
    assert HeuristicRouter(_config("b/cheap")).route("What is 2+2?").model.id == "b/cheap"


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError, match="OPENROUTER_API_KEY is not set"):
        create_provider("openrouter", {})


def test_openrouter_parses_usage(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
                "model": "x",
            },
        )

    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    resp = asyncio.run(provider.complete(CompletionRequest("x", [Message("user", "hi")])))
    assert resp.text == "hi"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 3


def test_invalid_tier_rejected():
    with pytest.raises(ConfigError):
        parse_config(
            {
                "models": [
                    {
                        "id": "m",
                        "provider": "openrouter",
                        "tier": "medium",
                        "input_usd_per_mtok": 1.0,
                        "output_usd_per_mtok": 1.0,
                    }
                ]
            }
        )


def test_repo_cora_toml_loads():
    cfg = load_config(Path("cora.toml"))
    tiers = {m.tier for m in cfg.models}
    assert "cheap" in tiers
    assert "strong" in tiers


def test_find_config_explicit_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cora.toml").write_text("", encoding="utf-8")
    explicit = tmp_path / "other.toml"
    explicit.write_text("", encoding="utf-8")
    assert find_config(explicit) == explicit


def test_find_config_uses_cwd_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    (work / "cora.toml").write_text("", encoding="utf-8")
    assert find_config(None).resolve() == (work / "cora.toml").resolve()


def test_find_config_falls_back_to_bundled_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    path = find_config(None)
    assert path.name == "cora.toml"
    assert path.is_file()
    assert load_config(path).models
