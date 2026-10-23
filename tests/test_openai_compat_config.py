from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from cora.cli.main import app
from cora.core.config import parse_config
from cora.core.errors import ConfigError
from cora.core.providers import create_provider
from cora.core.providers.openai_compat import OpenAICompatProvider
from cora.core.providers.openrouter import OpenRouterProvider

BASE = {
    "type": "openai_compat",
    "base_url": "https://example.test/v1",
    "api_key_env": "GEMINI_API_KEY",
}


def _data(section: dict | None = None) -> dict:
    providers = {} if section is None else {"gemini": section}
    return {
        "models": [
            {
                "id": "gemini-3.5-flash-lite",
                "provider": "gemini",
                "tier": "cheap",
                "input_usd_per_mtok": 0.0,
                "output_usd_per_mtok": 0.0,
            }
        ],
        "providers": providers,
    }


def test_type_resolves_openai_compat(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-DUMMY-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-DUMMY")
    gemini = create_provider("gemini", dict(BASE))
    assert isinstance(gemini, OpenAICompatProvider)
    assert isinstance(create_provider("openrouter", {}), OpenRouterProvider)


def test_unknown_type_config_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-DUMMY-key")
    with pytest.raises(ConfigError, match="unknown provider type 'nope'"):
        create_provider("gemini", {**BASE, "type": "nope"})


@pytest.mark.parametrize("key", ["base_url", "api_key_env"])
def test_missing_base_url_or_key_env(key):
    section = {k: v for k, v in BASE.items() if k != key}
    with pytest.raises(ConfigError, match=key):
        parse_config(_data(section))


def test_missing_base_url_cli_exit_2(tmp_path):
    cfg = tmp_path / "cora.toml"
    cfg.write_text(
        '[providers.gemini]\ntype = "openai_compat"\napi_key_env = "GEMINI_API_KEY"\n\n'
        '[[models]]\nid = "gemini-3.5-flash-lite"\nprovider = "gemini"\ntier = "cheap"\n'
        "input_usd_per_mtok = 0.0\noutput_usd_per_mtok = 0.0\nfree_tier = true\n\n"
        '[[models]]\nid = "gemini-3.1-flash-lite"\nprovider = "gemini"\ntier = "strong"\n'
        "input_usd_per_mtok = 0.0\noutput_usd_per_mtok = 0.0\nfree_tier = true\n",
        encoding="utf-8",
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(cfg)]
    )
    assert result.exit_code == 2
    assert "base_url" in json.loads(result.stdout)["errors"][0]


@pytest.mark.parametrize(
    "key,value",
    [("rpm_limit", 0), ("rpm_limit", 1.5), ("max_429_retries", -1), ("request_deadline_s", 0)],
)
def test_invalid_numbers(key, value):
    with pytest.raises(ConfigError):
        parse_config(_data({**BASE, key: value}))


def test_rpm_limit_absent_ok_and_retry_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-DUMMY-key")
    parse_config(_data(dict(BASE)))
    provider = OpenAICompatProvider(
        dict(BASE), transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    assert provider.max_429_retries == 4


def test_free_tier_parse():
    data = _data(dict(BASE))
    data["models"][0]["free_tier"] = "yes"
    with pytest.raises(ConfigError, match="free_tier"):
        parse_config(data)
    assert parse_config(_data(dict(BASE))).models[0].free_tier is False
