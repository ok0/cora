from __future__ import annotations

import asyncio
import difflib
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import cora.bench.live
from cora.cli.common import load_resolved
from cora.cli.main import app
from cora.core.errors import ProviderError
from cora.core.providers.base import ProviderTimeout, call_with_timeout
from cora.core.providers.openrouter import RETRY_DELAYS_S, OpenRouterProvider
from cora.core.types import CompletionRequest, Message

REPO = Path(__file__).resolve().parents[1]
ARMS = REPO / "tests" / "fixtures" / "m19" / "arms"
PREREG = REPO / "tests" / "fixtures" / "m19" / "preregistration.md"
CORA_TOML = REPO / "cora.toml"

PAIRS = {
    "deadline.toml": CORA_TOML,
    "deadline-cascade-strong.toml": ARMS / "cascade-strong.toml",
    "deadline-cascade-m1-m2.toml": ARMS / "cascade-m1-m2.toml",
    "deadline-deleg-nudge.toml": ARMS / "deleg-nudge.toml",
    "deadline-keys-on.toml": ARMS / "keys-on.toml",
}

REPLACEMENTS = [
    ("\ntimeout_s = 120\n", "\ntimeout_s = 300\n"),
    ("request_deadline_s = 90 ", "request_deadline_s = 300"),
    ("call_timeout_s = 300 ", "call_timeout_s = 960 "),
]

REQ = CompletionRequest("m/x", [Message("user", "hi")])
OK_JSON = {"choices": [{"message": {"content": "ok"}}], "usage": {}}


def _prereg_diff_block(name: str) -> list[str]:
    lines = PREREG.read_text(encoding="utf-8").splitlines()
    heading = f"#### 설정 {name}"
    start = lines.index(heading)
    open_idx = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("```diff"))
    close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i] == "```")
    return lines[open_idx + 1 : close_idx][2:]


@pytest.mark.parametrize("name", list(PAIRS))
def test_deadline_file_is_base_plus_three_values(name: str) -> None:
    base = PAIRS[name].read_text(encoding="utf-8")
    expected = base
    for old, new in REPLACEMENTS:
        assert base.count(old) == 1
        expected = expected.replace(old, new, 1)
    actual = (ARMS / name).read_text(encoding="utf-8")
    assert actual == expected


def test_deadline_diff_registered() -> None:
    base = CORA_TOML.read_text(encoding="utf-8").splitlines()
    fixture = (ARMS / "deadline.toml").read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(base, fixture, n=3, lineterm=""))[2:]
    assert diff == _prereg_diff_block("deadline")


@pytest.mark.parametrize("name", list(PAIRS))
def test_deadline_values_compose(name: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(ARMS / name, tmp_path)
    assert cfg.providers["openrouter"]["request_deadline_s"] == 300
    assert cfg.providers["openrouter"]["timeout_s"] == 300
    assert cfg.agent.call_timeout_s == 960
    run = cora.bench.live._run_config(cfg, "qwen/qwen3-coder-30b-a3b-instruct", "react", 30, 0.30)
    assert run.agent.call_timeout_s == 960
    p = OpenRouterProvider(run.providers["openrouter"])
    assert p.request_deadline_s == 300.0
    assert p.timeout_s == 300


def test_defaults_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(CORA_TOML, tmp_path)
    assert cfg.providers["openrouter"]["request_deadline_s"] == 90
    assert cfg.providers["openrouter"]["timeout_s"] == 120
    assert cfg.agent.call_timeout_s == 300


@pytest.mark.parametrize("name", list(PAIRS))
def test_coherence_rule(name: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(ARMS / name, tmp_path)
    d = cfg.providers["openrouter"]["request_deadline_s"]
    assert cfg.agent.call_timeout_s >= (len(RETRY_DELAYS_S) + 1) * d + sum(RETRY_DELAYS_S)


def test_provider_chain_ends_before_call_timeout(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")

    async def _noop_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("cora.core.providers.openrouter._sleep", _noop_sleep)
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        await asyncio.sleep(5)
        return httpx.Response(200, json=OK_JSON)

    p = OpenRouterProvider({"request_deadline_s": 0.1}, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as exc:
        asyncio.run(call_with_timeout(lambda: p.complete(REQ), model="m", timeout_s=0.5))
    assert not isinstance(exc.value, ProviderTimeout)
    assert "RequestDeadlineExceeded" in str(exc.value)
    assert len(calls) == 3

    calls.clear()
    with pytest.raises(ProviderTimeout):
        asyncio.run(call_with_timeout(lambda: p.complete(REQ), model="m", timeout_s=0.15))


PLAN_CASES = [
    (
        "deadline.toml",
        None,
        [
            "--suite",
            "e2e",
            "--models",
            "deepseek/deepseek-v3.2",
            "--protocols",
            "react",
            "--e2e-task-cost",
            "0.30",
            "--tasks",
            "e2e_hx1",
            "--repeats",
            "1",
            "--max-cost",
            "0.30",
        ],
        "0.147302",
    ),
    (
        "deadline-cascade-strong.toml",
        "cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "google/gemini-2.5-flash-lite",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h01,e2e_h02",
            "--repeats",
            "3",
            "--max-cost",
            "0.42",
        ],
        "0.420000",
    ),
    (
        "deadline-cascade-strong.toml",
        "cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h01,e2e_h02",
            "--repeats",
            "3",
            "--max-cost",
            "0.42",
        ],
        "0.420000",
    ),
    (
        "deadline-deleg-nudge.toml",
        "deleg-nudge.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "deleg-on-par-on",
            "--tasks",
            "e2e_hx1,e2e_hx2",
            "--repeats",
            "3",
            "--max-cost",
            "0.39",
        ],
        "0.390000",
    ),
    (
        "deadline.toml",
        None,
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--tasks",
            "e2e_h04",
            "--repeats",
            "1",
            "--max-cost",
            "0.08",
        ],
        "0.042202",
    ),
    (
        "deadline.toml",
        None,
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--tasks",
            "e2e_h06",
            "--repeats",
            "1",
            "--max-cost",
            "0.07",
        ],
        "0.035168",
    ),
    (
        "deadline.toml",
        None,
        [
            "--suite",
            "e2e",
            "--models",
            "deepseek/deepseek-v3.2",
            "--protocols",
            "react",
            "--e2e-task-cost",
            "0.30",
            "--tasks",
            "e2e_h06",
            "--repeats",
            "1",
            "--max-cost",
            "0.30",
        ],
        "0.122752",
    ),
]


def _total_line(output: str) -> str:
    lines = [ln for ln in output.splitlines() if ln.startswith("total_max_usd:")]
    assert len(lines) == 1, output
    return lines[0]


@pytest.mark.parametrize(("name", "base", "args", "value"), PLAN_CASES)
def test_plan_total_unchanged(
    name: str, base: str | None, args: list[str], value: str, monkeypatch
) -> None:
    monkeypatch.chdir(REPO)
    env = {"OPENROUTER_API_KEY": "test-dummy"}
    base_argv = ["-c", str(ARMS / base)] if base is not None else []
    deadline = CliRunner().invoke(app, ["bench", "plan", "-c", str(ARMS / name), *args], env=env)
    base_run = CliRunner().invoke(app, ["bench", "plan", *base_argv, *args], env=env)
    assert deadline.exit_code == 0, deadline.output
    assert base_run.exit_code == 0, base_run.output
    assert _total_line(deadline.output) == _total_line(base_run.output)
    assert value in _total_line(deadline.output)
