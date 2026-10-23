from __future__ import annotations

import dataclasses
import json
import os
import shlex
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

from cora.core.config import CoraConfig, parse_config
from cora.core.providers import register_provider
from cora.core.types import (
    CompletionRequest,
    CompletionResponse,
    NativeToolCall,
    estimate_tokens,
    messages_tokens,
)


@register_provider("scripted")
class ScriptedProvider:
    script: ClassVar[list] = []
    calls: ClassVar[list[CompletionRequest]] = []

    def __init__(self, settings: Any) -> None:
        pass

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        ScriptedProvider.calls.append(req)
        if ScriptedProvider.script:
            item = ScriptedProvider.script.pop(0)
        else:
            item = "Final Answer: (script exhausted)"
        text = item(req) if callable(item) else item
        if isinstance(text, CompletionResponse):
            return text
        return CompletionResponse(
            text,
            messages_tokens(req.messages),
            estimate_tokens(text),
            req.model,
        )


@register_provider("scripted_stream")
class ScriptedStreamProvider(ScriptedProvider):
    async def stream(self, req, on_text):
        resp = await self.complete(req)
        for i in range(0, len(resp.text), 3):
            on_text(resp.text[i : i + 3])
        return resp


@pytest.fixture(autouse=True)
def scripted() -> type[ScriptedProvider]:
    ScriptedProvider.script.clear()
    ScriptedProvider.calls.clear()
    return ScriptedProvider


@pytest.fixture(autouse=True)
def _record_env_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORA_RECORD_MODE", raising=False)
    monkeypatch.delenv("CORA_RECORD_DIR", raising=False)


@pytest.fixture
def mock_config() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
                {
                    "id": "mock/strong",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def with_agent(config: CoraConfig, **overrides: Any) -> CoraConfig:
    return dataclasses.replace(config, agent=dataclasses.replace(config.agent, **overrides))


M16_KEYS_OFF = {
    "verify_before_final": False,
    "compile_check": False,
    "edge_case_prompt": False,
    "stub_check": False,
    "json_string_repair": False,
    "overwrite_guard": False,
}


def with_gates_off(config: CoraConfig, **overrides: Any) -> CoraConfig:
    return with_agent(config, **(M16_KEYS_OFF | overrides))


def write_files(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")


PY = shlex.quote(sys.executable)


COMPLEX_PROMPT = "Refactor the parser in a.py, then fix the failing tests in b.py and c.py"


def act(tool: str, args: dict) -> str:
    return f"Thought: step\nAction: {tool}\nAction Input: {json.dumps(args)}"


CFG_TOML = """
[[models]]
id = "mock/cheap"
provider = "scripted"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[[models]]
id = "mock/strong"
provider = "scripted"
tier = "strong"
input_usd_per_mtok = 5.0
output_usd_per_mtok = 10.0
"""


@pytest.fixture
def cfg_file(tmp_path) -> Path:
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML, encoding="utf-8")
    return path


GATES_OFF_TOML = "\n[agent]\n" + "".join(f"{key} = false\n" for key in M16_KEYS_OFF)


@pytest.fixture
def cfg_file_gates_off(tmp_path) -> Path:
    path = tmp_path / "cora_gates_off.toml"
    path.write_text(CFG_TOML + GATES_OFF_TOML, encoding="utf-8")
    return path


@pytest.fixture
def ws(tmp_path) -> Path:
    path = tmp_path / "ws"
    path.mkdir()
    return path


def run_repl(workdir, config, lines, *, approval="auto", verbose=False) -> str:
    from cora.cli.io import PlainIO
    from cora.cli.repl import Repl, ReplOptions

    out: list[str] = []
    feed = list(lines)

    def read(prompt: str) -> str:
        out.append(prompt)
        if not feed:
            raise EOFError
        item = feed.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    Repl(
        PlainIO(input_fn=read, write=out.append),
        ReplOptions(Path(workdir), Path(config), approval=approval, verbose=verbose),
    ).run()
    return "".join(out)


@register_provider("fixed_usage")
class FixedUsageProvider(ScriptedProvider):
    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        resp = await super().complete(req)
        return dataclasses.replace(resp, input_tokens=1000, output_tokens=100)


FIXED_CFG_TOML = CFG_TOML.replace('provider = "scripted"', 'provider = "fixed_usage"')


SLOW_DESELECTED = pytest.StashKey[int]()


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests marked 'live' (real OpenRouter calls; costs money)",
    )
    parser.addoption(
        "--full",
        action="store_true",
        default=False,
        help="also run tests marked 'slow' (TUI/PTY, install, subprocess, timing); "
             "same as CORA_FULL_TESTS=1",
    )


def pytest_collection_modifyitems(config, items):
    if not (config.getoption("--run-live") and os.environ.get("OPENROUTER_API_KEY")):
        skip = pytest.mark.skip(reason="live test: requires --run-live and OPENROUTER_API_KEY")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)
    if config.getoption("--full") or os.environ.get("CORA_FULL_TESTS") == "1":
        return
    slow = [item for item in items if "slow" in item.keywords]
    if slow:
        items[:] = [item for item in items if "slow" not in item.keywords]
        config.hook.pytest_deselected(items=slow)
        config.stash[SLOW_DESELECTED] = len(slow)


def pytest_terminal_summary(terminalreporter, config):
    n = config.stash.get(SLOW_DESELECTED, 0)
    if n:
        terminalreporter.write_line(
            f"fast run: {n} slow tests skipped (TUI/PTY, install, subprocess, timing); "
            "run `uv run pytest --full` for everything")


def tc(name, args, id="c1"):
    return NativeToolCall(id, name, args if isinstance(args, str) else json.dumps(args))


def native(*calls, text=""):
    return CompletionResponse(text, 10, 5, "mock/cheap", tool_calls=tuple(calls))


def with_decider(config: CoraConfig, **kw: Any) -> CoraConfig:
    return dataclasses.replace(config, decider=dataclasses.replace(config.decider, **kw))


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    attempts: list[str] = []

    def blocked(name: str):
        def block(*args: Any, **kwargs: Any) -> None:
            attempts.append(name)
            raise AssertionError("network access attempted in an offline test")

        return block

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", blocked("socket.create_connection"))
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked("httpx.handle_request"))
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport,
        "handle_async_request",
        blocked("httpx.handle_async_request"),
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    yield attempts
    assert attempts == []
