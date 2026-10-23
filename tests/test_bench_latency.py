from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, ScriptedProvider, act
from cora.bench.live import bench_clock, run_ab_bench, run_live_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.report import report_json, report_markdown
from cora.cli.main import app
from cora.core.config import BenchSettings, parse_config
from cora.core.errors import ConfigError
from cora.core.providers import register_provider
from cora.core.providers.openrouter import OpenRouterProvider
from explore_mock import ExploreMock, explore_config

DURATIONS: list[float] = []


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


CLOCK = FakeClock()


@register_provider("clocked")
class ClockedProvider(ScriptedProvider):
    async def complete(self, req):
        CLOCK.t += DURATIONS.pop(0)
        return await super().complete(req)


@pytest.fixture(autouse=True)
def _real_network_forbidden(monkeypatch):
    reached: list[str] = []

    async def forbidden(self, request):
        reached.append(str(request.url))
        raise RuntimeError(f"real network reached in test: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    yield
    assert reached == []


class OnePool:
    def __init__(self, provider) -> None:
        self.provider = provider

    def get(self, name: str):
        return self.provider


def _task(i: str) -> LiveTask:
    return LiveTask(
        f"t{i}",
        "explore",
        "q",
        {"f.txt": "x"},
        answer_regex=r"\b42\b",
    )


def test_cell_latency_includes_retries_and_backoff(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")
    clock = FakeClock()
    posts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/auth/key"):
            return httpx.Response(200, json={"data": {"limit_remaining": None}})
        if request.method == "GET" and request.url.path.endswith("/credits"):
            return httpx.Response(200, json={"data": {"total_credits": 1, "total_usage": 0}})
        clock.t += 40
        posts["n"] += 1
        if posts["n"] <= 2:
            return httpx.Response(500, text="server error")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Final Answer: 42"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.00001},
            },
        )

    async def fake_sleep(d):
        clock.t += d

    monkeypatch.setattr("cora.core.providers.openrouter._sleep", fake_sleep)
    provider = OpenRouterProvider({}, transport=httpx.MockTransport(handler))
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "test/cheap",
                    "provider": "openrouter",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )
    report = asyncio.run(
        run_live_bench(
            cfg,
            models=["test/cheap"],
            protocols=["react"],
            tasks=[_task("1")],
            max_cost_usd=0.3,
            max_task_cost_usd=0.1,
            max_iterations=4,
            state_dir=tmp_path / "s",
            providers=OnePool(provider),
            clock=clock,
        )
    )
    r = report.results[0]
    assert r.status == "solved"
    assert r.latency_s >= 123
    assert r.call_latencies_s == [pytest.approx(123.0)]
    assert report.wall_s >= sum(x.latency_s for x in report.results)
    assert json.loads(report_json(report, None))["latency"]["cells"][0]["stall"] is True


def test_call_latency_stats_and_stall_threshold(tmp_path, scripted):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "clocked",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )

    def run(threshold: float):
        scripted.script[:] = [act("list_files", {}), "Final Answer: 42", "Final Answer: 42"]
        DURATIONS[:] = [1, 3, 70]
        return asyncio.run(
            run_live_bench(
                cfg,
                models=["mock/cheap"],
                protocols=["react"],
                tasks=[_task("1"), _task("2")],
                max_cost_usd=0.3,
                max_task_cost_usd=0.1,
                max_iterations=4,
                state_dir=tmp_path / f"s{threshold}",
                stall_threshold_s=threshold,
                clock=CLOCK,
            )
        )

    report = run(60)
    data = json.loads(report_json(report, None))
    cells = {c["task"]: c for c in data["latency"]["cells"]}
    assert cells["t1"]["calls"] == 2
    assert cells["t1"]["p50_s"] == 2.0
    assert cells["t1"]["max_s"] == 3.0
    assert cells["t1"]["stalled_calls"] == 0
    assert cells["t1"]["stall"] is False
    assert cells["t2"]["calls"] == 1
    assert cells["t2"]["p50_s"] == 70.0
    assert cells["t2"]["stalled_calls"] == 1
    assert cells["t2"]["stall"] is True
    config = data["latency"]["configs"][0]
    assert config["config"] == "mock/cheap react"
    assert config["calls"] == 3
    assert config["p50_s"] == 3.0
    assert config["max_s"] == 70.0
    assert config["stalled_calls"] == 1
    markdown = report_markdown(report, None)
    assert "### Call latency" in markdown
    assert "| t2 | mock/cheap react | 1 | 70.00 | 70.00 | 1 | STALL |" in markdown
    assert data["settings"]["stall_threshold_s"] == 60.0

    report = run(100)
    data = json.loads(report_json(report, None))
    assert all(c["stall"] is False for c in data["latency"]["cells"])
    assert "100s" in report_markdown(report, None)
    assert report.settings["stall_threshold_s"] == 100.0


def test_ab_latency_by_arm(tmp_path):
    ExploreMock.reset()
    ExploreMock.usage = (1000, 100)
    ExploreMock.main = ["Final Answer: 42", "Final Answer: 42"]
    report = asyncio.run(
        run_ab_bench(
            explore_config(),
            arms=["deleg-off", "strong-only"],
            model="mock/cheap",
            protocol="react",
            tasks=[_task("1")],
            max_cost_usd=0.3,
            max_task_cost_usd=0.1,
            max_iterations=4,
            state_dir=tmp_path / "state",
        )
    )
    latency = json.loads(report_json(report, None))["latency"]
    assert [c["config"] for c in latency["configs"]] == ["deleg-off", "strong-only"]
    assert [c["calls"] for c in latency["configs"]] == [1, 1]


def test_stall_threshold_config():
    model = {
        "id": "mock/cheap",
        "provider": "scripted",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    }
    with pytest.raises(ConfigError, match="stall_threshold_s"):
        parse_config({"models": [model], "bench": {"stall_threshold_s": 0}})
    cfg = parse_config({"models": [model], "bench": {"stall_threshold_s": 5}})
    assert cfg.bench.stall_threshold_s == 5
    assert BenchSettings().stall_threshold_s == 60.0


def test_cli_passes_stall_threshold(tmp_path, scripted):
    cfg_path = tmp_path / "cora.toml"
    cfg_path.write_text(CFG_TOML + "\n[bench]\nstall_threshold_s = 7\n", encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    out = tmp_path / "out"
    scripted.script[:] = ["Final Answer: 8731"]
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg_path),
            "-w",
            str(ws),
            "--models",
            "mock/cheap",
            "--protocols",
            "react",
            "--tasks",
            "explore_find_port",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stderr
    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["settings"]["stall_threshold_s"] == 7.0
    assert data["latency"]["stall_threshold_s"] == 7.0


def test_bench_clock_monotonic():
    a = bench_clock()
    b = bench_clock()
    assert b >= a
