from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, ClassVar

import pytest

from conftest import CFG_TOML, ScriptedProvider, with_agent
from cora.bench.e2e import load_e2e_tasks
from cora.bench.live import run_live_bench
from cora.core.agent import Agent
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.config import ConfigError, parse_config
from cora.core.metering import CostMeter
from cora.core.outcome import exit_code
from cora.core.planner import generate_plan
from cora.core.providers import register_provider
from cora.core.providers.base import ProviderTimeout, call_with_timeout
from cora.core.state import SessionStore, StopReason
from cora.core.tools import ApprovalPolicy
from test_headless import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
TASK = "hi"
GATE_KEYS = ("verify_before_final", "compile_check", "edge_case_prompt", "stub_check")


@register_provider("m16c_stall")
class StallProvider(ScriptedProvider):
    async def complete(self, req):
        await asyncio.sleep(3600)


@register_provider("m16c_stall_stream")
class StallStreamProvider(ScriptedProvider):
    async def stream(self, req, on_text):
        on_text("Thought: ")
        await asyncio.sleep(3600)


@register_provider("m16c_once")
class OnceProvider(ScriptedProvider):
    attempts: ClassVar[int] = 0

    async def complete(self, req):
        OnceProvider.attempts += 1
        if OnceProvider.attempts == 1:
            await asyncio.sleep(3600)
        return await super().complete(req)


@pytest.fixture(autouse=True)
def _reset_once() -> None:
    OnceProvider.attempts = 0


def _cfg(provider: str, **agent: Any):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": provider,
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
    return with_agent(cfg, approval="auto", **agent)


def _parse(agent: dict | None = None):
    data: dict[str, Any] = {
        "models": [
            {
                "id": "mock/cheap",
                "provider": "scripted",
                "tier": "cheap",
                "input_usd_per_mtok": 1.0,
                "output_usd_per_mtok": 2.0,
            }
        ]
    }
    if agent is not None:
        data["agent"] = agent
    return parse_config(data)


def _events(r, kind: str) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if e["type"] == kind]


def _run(cfg, ws: Path, on_answer_delta=None):
    agent = Agent(cfg, ws, ApprovalPolicy("auto"), on_answer_delta=on_answer_delta)
    return asyncio.run(agent.run(TASK))


def test_call_timeout_default():
    assert _parse().agent.call_timeout_s == 300
    for path in (ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml"):
        text = path.read_text(encoding="utf-8")
        assert "call_timeout_s = 300" in text
        for key in GATE_KEYS:
            assert f"{key} = true" in text


@pytest.mark.parametrize("value", [9, 3601, "x", True, 0, None, 30.5])
def test_call_timeout_invalid(value):
    with pytest.raises(ConfigError):
        _parse({"call_timeout_s": value})


@pytest.mark.parametrize("value", [10, 3600])
def test_call_timeout_bounds_ok(value):
    assert _parse({"call_timeout_s": value}).agent.call_timeout_s == value


@pytest.mark.parametrize("key", GATE_KEYS)
@pytest.mark.parametrize("value", ["yes", 1])
def test_gate_key_invalid(key, value):
    with pytest.raises(ConfigError):
        _parse({key: value})


def test_unknown_agent_key():
    with pytest.raises(ConfigError):
        _parse({"bogus": 1})


@pytest.mark.parametrize(
    "extra, needle",
    [
        ("[agent]\ncall_timeout_s = 9", "call_timeout_s"),
        ("[agent]\nbogus = 1", "bogus"),
    ],
)
def test_agent_key_invalid_exit_2(extra, needle, ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n" + extra)
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2
    assert needle in result.output


def test_stall_retries_once_then_provider_timeout(ws):
    cfg = _cfg("m16c_stall", call_timeout_s=0.05)
    started = time.monotonic()
    r = _run(cfg, ws)
    elapsed = time.monotonic() - started

    assert r.stop_reason == StopReason.PROVIDER_TIMEOUT
    assert exit_code("provider_timeout") == 1
    assert len(_events(r, "call_timeout")) == 2
    timeouts = _events(r, "provider_timeout")
    assert len(timeouts) == 1
    assert timeouts[0]["model"] == "mock/cheap"
    assert timeouts[0]["timeout_s"] == 0.05
    assert r.session.stop_reason == "provider_timeout"
    saved = SessionStore(r.log_path.parent.parent).load(r.session.id)
    assert saved.stop_reason == "provider_timeout"
    assert elapsed < 2


def test_stream_stall_after_partial(ws):
    cfg = _cfg("m16c_stall_stream", call_timeout_s=0.05)
    started = time.monotonic()
    r = _run(cfg, ws, on_answer_delta=lambda s: None)
    elapsed = time.monotonic() - started

    assert r.stop_reason == StopReason.PROVIDER_TIMEOUT
    assert exit_code("provider_timeout") == 1
    assert len(_events(r, "call_timeout")) == 2
    timeouts = _events(r, "provider_timeout")
    assert len(timeouts) == 1
    assert timeouts[0]["model"] == "mock/cheap"
    assert timeouts[0]["timeout_s"] == 0.05
    assert r.session.stop_reason == "provider_timeout"
    saved = SessionStore(r.log_path.parent.parent).load(r.session.id)
    assert saved.stop_reason == "provider_timeout"
    assert elapsed < 2


def test_timeout_once_then_answer(ws, scripted):
    scripted.script[:] = ["Final Answer: ok"]
    cfg = _cfg("m16c_once", call_timeout_s=0.05)
    r = _run(cfg, ws)

    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "ok"
    assert len(_events(r, "call_timeout")) == 1
    assert _events(r, "provider_timeout") == []


def test_wall_cap_still_enforced(ws):
    cfg = _cfg("m16c_stall", call_timeout_s=5, max_wall_s=0.2)
    started = time.monotonic()
    r = _run(cfg, ws)
    elapsed = time.monotonic() - started

    assert r.stop_reason == StopReason.BUDGET_EXCEEDED
    trips = _events(r, "budget_trip")
    assert any(t["cap"] == "wall" for t in trips)
    assert _events(r, "provider_timeout") == []
    assert elapsed < 2


def test_call_with_timeout_passes_through_inner_timeout():
    calls: list[int] = []

    async def inner():
        calls.append(1)
        raise TimeoutError("inner")

    with pytest.raises(TimeoutError) as info:
        asyncio.run(call_with_timeout(inner, model="mock/cheap", timeout_s=5))
    assert not isinstance(info.value, ProviderTimeout)
    assert len(calls) == 1


def test_planner_uses_call_timeout():
    cfg = _cfg("m16c_stall", call_timeout_s=0.05)
    gov = BudgetGovernor(BudgetLimits(cost_usd=1.0, iterations=30, wall_s=None, tool_calls=None))
    with pytest.raises(ProviderTimeout):
        asyncio.run(generate_plan("g", cfg, gov, meter=CostMeter(), max_milestones=8))


@pytest.mark.slow
def test_bench_run_inherits_timeout(tmp_path):
    todo = {t.id: t for t in load_e2e_tasks()}["e2e_todo_cli"]
    cfg = _cfg("m16c_stall", call_timeout_s=0.05)
    report = asyncio.run(
        run_live_bench(
            cfg,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[todo],
            max_cost_usd=0.30,
            max_task_cost_usd=0.30,
            max_iterations=40,
            state_dir=tmp_path / "bench",
        )
    )
    assert report.results[0].end_reason == "provider_timeout"
