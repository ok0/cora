from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from cora.cli.main import app
from cora.core.config import load_config, parse_config
from cora.core.errors import ConfigError, MissingAPIKeyError
from cora.core.observability import read_events
from cora.core.providers import ProviderPool, openai_compat

ROOT = Path(__file__).resolve().parents[1]
DUMMY_OR = "sk-or-test-DUMMY-lazy"
DUMMY_GM = "gm-test-DUMMY-leakcheck"
ROUTER_MARK = "[router]\n"
PIN_LINE = 'pin = "gemini-3.5-flash-lite"\n'


def _pinned_config(tmp_path: Path, *, native: bool = False) -> Path:
    text = (ROOT / "cora.toml").read_text(encoding="utf-8")
    assert text.count(ROUTER_MARK) == 1
    text = text.replace(ROUTER_MARK, ROUTER_MARK + PIN_LINE)
    if native:
        text = text.replace('tool_protocol = "react"', 'tool_protocol = "native"')
    path = tmp_path / "cora.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _or_ok_response(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(
            200, json={"data": {"limit_remaining": None}}, request=request
        )
    body = json.loads(request.content)
    payload = {
        "choices": [{"message": {"content": "Final Answer: ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00001},
        "model": "google/gemini-2.5-flash-lite",
    }
    if body.get("stream"):
        text = f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n"
        return httpx.Response(
            200,
            content=text.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
            request=request,
        )
    return httpx.Response(200, json=payload, request=request)


def test_pool_is_lazy(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY_OR)
    cfg = load_config(ROOT / "cora.toml")
    pool = ProviderPool(cfg)
    assert pool.get("openrouter") is not None
    with pytest.raises(MissingAPIKeyError, match="GEMINI_API_KEY"):
        pool.get("gemini")
    with pytest.raises(KeyError):
        pool.get("x")


def test_pool_still_rejects_unknown_provider_eagerly():
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "m",
                    "provider": "nope",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 1.0,
                }
            ]
        }
    )
    with pytest.raises(ConfigError):
        ProviderPool(cfg)


def test_default_config_run_without_gemini_key(monkeypatch, no_network, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY_OR)
    monkeypatch.setattr(httpx.AsyncClient, "send", _fake_send_or)
    ws = _ws(tmp_path)
    result = CliRunner().invoke(
        app,
        ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(ROOT / "cora.toml")],
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


async def _fake_send_or(self, request, **kw):
    return _or_ok_response(request)


def test_gemini_selected_without_key_exit_2(monkeypatch, no_network, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY_OR)
    cfg = _pinned_config(tmp_path)
    ws = _ws(tmp_path)

    async def must_not_send(self, request, **kw):
        raise AssertionError("no HTTP request expected without GEMINI_API_KEY")

    monkeypatch.setattr(httpx.AsyncClient, "send", must_not_send)
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(cfg)]
    )
    assert result.exit_code == 2
    errors = json.loads(result.stdout)["errors"]
    assert "GEMINI_API_KEY" in errors[0]
    assert DUMMY_GM not in errors[0]
    assert "gm-test" not in errors[0]


def test_dummy_key_never_leaks(monkeypatch, no_network, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GM)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = _pinned_config(tmp_path, native=True)
    ws = _ws(tmp_path)
    extra = {"google": {"thought_signature": "sig-leakcheck=="}}
    state = {"calls": 0}

    async def fake(self, request, **kw):
        if request.method == "GET":
            return httpx.Response(200, json={}, request=request)
        state["calls"] += 1
        body = json.loads(request.content)
        if state["calls"] == 1:
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "list_files", "arguments": "{}"},
                                    "extra_content": extra,
                                }
                            ],
                        }
                    }
                ]
            }
            return httpx.Response(200, json=payload, request=request)
        echoed = [
            c.get("extra_content")
            for m in body["messages"]
            for c in m.get("tool_calls") or []
        ]
        assert extra in echoed
        payload = {"choices": [{"message": {"content": "Final Answer: ok"}}]}
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", fake)
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(cfg)]
    )
    assert result.exit_code == 0, result.stderr
    assert DUMMY_GM not in result.stdout
    assert DUMMY_GM not in result.stderr
    for path in (ws / ".cora").rglob("*"):
        if path.is_file():
            assert DUMMY_GM not in path.read_text(encoding="utf-8", errors="replace"), path


def test_rate_limited_headless_exit_1(monkeypatch, no_network, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GM)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = _pinned_config(tmp_path)
    ws = _ws(tmp_path)

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(openai_compat, "_sleep", no_sleep)

    async def always_429(self, request, **kw):
        if request.method == "GET":
            return httpx.Response(200, json={}, request=request)
        return httpx.Response(429, text="slow down", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", always_429)
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(cfg)]
    )
    assert result.exit_code == 1
    d = json.loads(result.stdout)
    assert "rate limited" in d["errors"][0]
    session_dirs = list((ws / ".cora" / "sessions").iterdir())
    assert len(session_dirs) == 1
    events = read_events(session_dirs[0] / "events.jsonl")
    limited = [e for e in events if e["type"] == "rate_limited"]
    assert len(limited) == 5
    assert sum(1 for e in limited if e["retrying"]) == 4
    assert sum(1 for e in limited if not e["retrying"]) == 1
