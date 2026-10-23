from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from conftest import COMPLEX_PROMPT, with_decider
from cora.bench.decider_eval import load_cases, run_decider_eval
from cora.bench.preflight import PreflightRefused
from cora.cli.main import app
from cora.core.errors import ConfigError, ProviderAccountError
from cora.core.providers.openrouter import openrouter_account_status
from cora.core.types import CompletionResponse

pytestmark = pytest.mark.usefixtures("no_network")

CASES = "\n".join(
    json.dumps(case)
    for case in (
        {"id": "a", "expected": "cheap", "prompt": "What is 2+2?",
         "tokens": {"input": 1000000, "output": 0},
         "replay": {"label": "cheap", "confidence": 0.9, "cost_usd": 0.001}},
        {"id": "b", "expected": "strong", "prompt": COMPLEX_PROMPT,
         "tokens": {"input": 1000000, "output": 0},
         "replay": {"label": "strong", "confidence": 0.95, "cost_usd": 0.001}},
        {"id": "c", "expected": "strong", "features": {"chars": 50},
         "tokens": {"input": 1000000, "output": 0},
         "replay": {"label": "strong", "confidence": 0.8, "cost_usd": 0.001}},
        {"id": "d", "expected": "cheap",
         "features": {"chars": 500, "code_keywords": True, "code_reference": True},
         "tokens": {"input": 2000000, "output": 0},
         "replay": {"label": "cheap", "confidence": 0.5, "cost_usd": 0.001}},
    )
) + "\n"


class FakePool:
    def __init__(self, get) -> None:
        self.get = get


class FakeProvider:
    def __init__(self, reply: str = '{"answer":"cheap","confidence":0.9}') -> None:
        self.reply = reply

    async def complete(self, req):
        return CompletionResponse(self.reply, 100, 10, req.model)


@pytest.fixture(autouse=True)
def no_provider_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising_factory(cfg):
        raise AssertionError("this eval must not build a provider pool")

    monkeypatch.setattr("cora.bench.decider_eval.ProviderPool", raising_factory)


@pytest.fixture
def cases_file(tmp_path) -> Path:
    path = tmp_path / "c.jsonl"
    path.write_text(CASES, encoding="utf-8")
    return path


def test_cli_heuristic_hand_computed(cfg_file, ws, scripted, cases_file) -> None:
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(cases_file), "--decider", "heuristic",
         "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 0, result.output
    for line in (
        "agreement: 2/4 (50.0%)",
        "misroutes: cheap->strong=1 strong->cheap=1",
        "fallbacks: 0 low_confidence: 0",
        "decision_cost_usd: 0.000000",
        "expected_model_cost_usd: 17.000000 (expected labels: 13.000000)",
        "expected_total_cost_usd: 17.000000",
    ):
        assert line in result.output, line
    assert scripted.calls == []


def test_cli_replay_hand_computed(cfg_file, ws, scripted, cases_file) -> None:
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(cases_file), "--decider", "replay",
         "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 0, result.output
    for line in (
        "agreement: 3/4 (75.0%)",
        "misroutes: cheap->strong=1 strong->cheap=0",
        "fallbacks: 0 low_confidence: 1",
        "decision_cost_usd: 0.004000",
        "expected_model_cost_usd: 21.000000 (expected labels: 13.000000)",
        "expected_total_cost_usd: 21.004000",
    ):
        assert line in result.output, line
    assert scripted.calls == []


def test_cli_json(cfg_file, ws, scripted, cases_file) -> None:
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(cases_file), "--decider", "heuristic",
         "--json", "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["agree"] == 2
    assert scripted.calls == []


def test_llm_without_live_refuses(cfg_file, ws, scripted, cases_file) -> None:
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(cases_file), "--decider", "llm",
         "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 2
    assert "--live" in result.output
    assert "nothing was called" in result.output
    assert scripted.calls == []


@pytest.mark.parametrize(
    "args",
    [
        ["decider", "foo", "--cases", "CASES"],
        ["decider", "eval"],
        ["decider", "eval", "--cases", "CASES", "--decider", "heuristic", "--live"],
    ],
)
def test_usage_errors(args, cfg_file, ws, cases_file) -> None:
    argv = [str(cases_file) if a == "CASES" else a for a in args]
    argv += ["-c", str(cfg_file), "-w", str(ws)]
    result = CliRunner().invoke(app, argv)
    assert result.exit_code == 2, result.output


def test_bad_case_line_reports_location(cfg_file, ws, tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"expected":"medium","prompt":"x"}\n', encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(path), "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 2
    assert ":1:" in result.output


def test_llm_opt_in_preflight_before_calls(mock_config, tmp_path) -> None:
    order: list[str] = []
    path = tmp_path / "c.jsonl"
    path.write_text(CASES, encoding="utf-8")

    class FakeAccount:
        async def account_get(self, path: str):
            order.append("account:" + path)
            if path == "/auth/key":
                return 200, {"data": {"limit_remaining": 1.0}}
            return 200, {"data": {}}

        async def account_status(self):
            return await openrouter_account_status(self.account_get)

    class OrderedProvider(FakeProvider):
        async def complete(self, req):
            order.append("complete")
            return await super().complete(req)

    provider = OrderedProvider()
    cfg = with_decider(mock_config, kind="llm")
    report = asyncio.run(
        run_decider_eval(
            cfg,
            load_cases(path),
            "llm",
            providers=FakePool(lambda name: provider),
            account={"scripted": FakeAccount()},
            max_cost_usd=0.05,
        )
    )
    assert order[0] == "account:/auth/key"
    assert order.index("complete") > order.index("account:/auth/key")
    assert report.cases == 4
    assert report.model == "mock/cheap"


def test_llm_preflight_refusal_blocks_calls(mock_config, tmp_path) -> None:
    order: list[str] = []
    path = tmp_path / "c.jsonl"
    path.write_text(CASES, encoding="utf-8")

    class LowLimitAccount:
        async def account_get(self, path: str):
            order.append("account:" + path)
            return 200, {"data": {"limit_remaining": 0.01}}

        async def account_status(self):
            return await openrouter_account_status(self.account_get)

    class OrderedProvider(FakeProvider):
        async def complete(self, req):
            order.append("complete")
            return await super().complete(req)

    provider = OrderedProvider()
    cfg = with_decider(mock_config, kind="llm")
    with pytest.raises(PreflightRefused):
        asyncio.run(
            run_decider_eval(
                cfg,
                load_cases(path),
                "llm",
                providers=FakePool(lambda name: provider),
                account={"scripted": LowLimitAccount()},
                max_cost_usd=0.05,
            )
        )
    assert "complete" not in order


def test_llm_max_cost_cap(mock_config, tmp_path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text(CASES, encoding="utf-8")
    cfg = with_decider(mock_config, kind="llm")
    with pytest.raises(ConfigError):
        asyncio.run(
            run_decider_eval(
                cfg,
                load_cases(path),
                "llm",
                providers=FakePool(lambda name: FakeProvider()),
                max_cost_usd=0.6,
            )
        )


def test_cli_llm_live_abort_exit3(cfg_file, ws, cases_file, monkeypatch) -> None:
    class AbortProvider:
        async def complete(self, req):
            raise ProviderAccountError(402, "x")

    monkeypatch.setattr(
        "cora.bench.decider_eval.ProviderPool",
        lambda cfg: FakePool(lambda name: AbortProvider()),
    )
    result = CliRunner().invoke(
        app,
        ["decider", "eval", "--cases", str(cases_file), "--decider", "llm", "--live",
         "-c", str(cfg_file), "-w", str(ws)],
    )
    assert result.exit_code == 3, result.output
    assert "aborted" in result.output


def test_no_network_fixture_catches(no_network) -> None:
    with pytest.raises(AssertionError):
        httpx.Client().get("https://example.com")
    assert no_network
    no_network.clear()
