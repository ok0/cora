from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from cora.bench.live import run_ab_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.preflight import PreflightRefused, run_preflight
from cora.bench.report import report_markdown
from cora.cli.main import app
from cora.core.config import parse_config
from cora.core.errors import ProviderAccountError
from cora.core.providers.openrouter import openrouter_account_status
from explore_mock import ExploreMock

DUMMY = "sk-or-v1-DUMMY-not-a-real-key-000"

CONFIG_TOML = """
[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"

[[models]]
id = "test/cheap"
provider = "openrouter"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0
supports_tools = true

[[models]]
id = "test/strong"
provider = "openrouter"
tier = "strong"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[bench]
models = ["test/cheap"]
"""

FINAL_BODY = {
    "choices": [{"message": {"content": "Final Answer: 8731"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00001},
    "model": "test/cheap",
}


@pytest.fixture(autouse=True)
def _real_network_forbidden(monkeypatch):
    reached: list[str] = []

    async def forbidden(self, request):
        reached.append(str(request.url))
        raise RuntimeError(f"real network reached in test: {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    yield
    assert reached == []


class Fake:
    def __init__(self) -> None:
        self.key_status = 200
        self.key_json: dict = {"data": {"limit_remaining": None}}
        self.key_exc: Exception | None = None
        self.credits_status = 200
        self.credits_json: dict = {"data": {"total_credits": 1.0, "total_usage": 0.1}}
        self.credits_exc: Exception | None = None
        self.chat: list[tuple[int, object]] = []
        self.posts = 0
        self.gets = 0


@pytest.fixture
def fake(monkeypatch) -> Fake:
    state = Fake()

    async def send(client_self, request, **kw):
        auth = request.headers.get("authorization", "")
        if request.method == "GET":
            state.gets += 1
            if request.url.path.endswith("/auth/key"):
                if state.key_exc is not None:
                    raise state.key_exc
                if state.key_status >= 300:
                    return httpx.Response(state.key_status, text=f"bad {auth}", request=request)
                return httpx.Response(state.key_status, json=state.key_json, request=request)
            if request.url.path.endswith("/credits"):
                if state.credits_exc is not None:
                    raise state.credits_exc
                if state.credits_status >= 300:
                    return httpx.Response(state.credits_status, text=f"bad {auth}", request=request)
                return httpx.Response(
                    state.credits_status, json=state.credits_json, request=request
                )
            raise AssertionError(f"unexpected GET {request.url}")
        state.posts += 1
        status, body = state.chat.pop(0) if state.chat else (200, FINAL_BODY)
        if isinstance(body, dict):
            return httpx.Response(status, json=body, request=request)
        return httpx.Response(status, text=str(body).replace("{auth}", auth), request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return state


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY)
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CONFIG_TOML, encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    return cfg, ws, tmp_path / "out"


def invoke(cfg: Path, ws: Path, out: Path, tasks: str = "explore_find_port", extra=()):
    return CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(ws),
            "--protocols",
            "react",
            "--tasks",
            tasks,
            "--out",
            str(out),
            *extra,
        ],
    )


def assert_no_leak(result, out: Path) -> None:
    assert DUMMY not in result.stdout
    assert DUMMY not in result.stderr
    for path in out.rglob("*"):
        if path.is_file():
            assert DUMMY not in path.read_text(encoding="utf-8", errors="replace"), path


def test_preflight_refuses_limit_below_cap(fake, setup):
    cfg, ws, out = setup
    fake.key_json = {"data": {"limit_remaining": 0.05}}
    result = invoke(cfg, ws, out)
    assert result.exit_code == 2, result.stderr
    assert fake.posts == 0
    assert "limit_remaining" in result.stderr
    assert "below this run's cap" in result.stderr
    assert not (out / "report.json").exists()
    assert_no_leak(result, out)


def test_preflight_refuses_expired_key(fake, setup):
    cfg, ws, out = setup
    fake.key_json = {"data": {"limit_remaining": None, "expires_at": "2020-01-01T00:00:00Z"}}
    result = invoke(cfg, ws, out)
    assert result.exit_code == 2, result.stderr
    assert "expired" in result.stderr
    assert fake.posts == 0
    assert_no_leak(result, out)


def test_preflight_unlimited_starts(fake, setup):
    cfg, ws, out = setup
    result = invoke(cfg, ws, out)
    assert result.exit_code == 0, result.stderr
    assert fake.posts >= 1
    assert_no_leak(result, out)


@pytest.mark.parametrize(
    "credits",
    [
        {"credits_json": {"data": {"total_credits": 0, "total_usage": 0.199}}},
        {"credits_status": 500},
        {"credits_exc": httpx.ConnectError("x")},
    ],
)
def test_credits_zero_or_error_does_not_block(fake, setup, credits):
    cfg, ws, out = setup
    for name, value in credits.items():
        setattr(fake, name, value)
    result = invoke(cfg, ws, out)
    assert result.exit_code == 0, result.stderr
    assert fake.posts >= 1
    assert_no_leak(result, out)


def test_auth_key_network_error_warns_and_continues(fake, setup):
    cfg, ws, out = setup
    fake.key_exc = httpx.ConnectError(f"boom {DUMMY}")
    result = invoke(cfg, ws, out)
    assert result.exit_code == 0, result.stderr
    assert "warning: key check failed" in result.stderr
    assert fake.posts >= 1
    assert_no_leak(result, out)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_key_401_403_refuses(fake, setup, status):
    cfg, ws, out = setup
    fake.key_status = status
    result = invoke(cfg, ws, out)
    assert result.exit_code == 2, result.stderr
    assert f"HTTP {status}" in result.stderr
    assert fake.posts == 0
    assert_no_leak(result, out)


@pytest.mark.parametrize("status", [402, 401, 403])
def test_mid_run_status_aborts(fake, setup, status):
    cfg, ws, out = setup
    fake.chat = [(200, FINAL_BODY), (status, "bad {auth}")]
    result = invoke(cfg, ws, out, tasks="explore_find_port,explore_count_todos,explore_find_raiser")
    assert result.exit_code == 3, result.stderr
    assert fake.posts == 2
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in report["results"]] == ["solved", "error", "not_run"]
    assert report["aborted"].startswith(f"HTTP {status}")
    assert report["cells"] == {"executed": 2, "not_run": 1, "skipped_budget": 0}
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert any(line.startswith(f"aborted: HTTP {status}") for line in markdown.splitlines())
    assert "| not_run |" in markdown
    assert "live bench aborted" in result.stderr
    assert_no_leak(result, out)


def _ab_config():
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "explore_mock",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": "explore_mock",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto"},
            "delegation": {"enabled": True},
        }
    )


def _qtask(i: str) -> LiveTask:
    return LiveTask(
        f"t{i}",
        "query",
        "q",
        {"f.txt": "x"},
        answer_regex=r"\b42\b",
    )


def test_ab_abort_stops_calls(tmp_path):
    ExploreMock.reset()
    ExploreMock.usage = (1000, 100)
    ExploreMock.main = [
        "Final Answer: 42",
        ProviderAccountError(402, "openrouter HTTP 402: no credits"),
    ]
    report = asyncio.run(
        run_ab_bench(
            _ab_config(),
            arms=["deleg-off", "strong-only"],
            model="mock/cheap",
            protocol="react",
            tasks=[_qtask("1"), _qtask("2")],
            max_cost_usd=0.3,
            max_task_cost_usd=0.1,
            max_iterations=4,
            state_dir=tmp_path / "state",
        )
    )
    assert len(ExploreMock.calls) == 2
    assert [r.status for r in report.results] == ["solved", "error", "not_run", "not_run"]
    assert report.aborted == "HTTP 402 from the provider (insufficient credits)"
    assert "aborted: HTTP 402" in report_markdown(report, None)


def _acct(routes: dict):
    class Acct:
        display_name = "OpenRouter"

        async def account_get(self, path: str):
            value = routes[path]
            if isinstance(value, BaseException):
                raise value
            return value

        async def account_status(self):
            return await openrouter_account_status(self.account_get)

    return {"openrouter": Acct()}


def test_run_preflight_unit():
    ok = {"/auth/key": (200, {"data": {"limit_remaining": None}}), "/credits": (500, None)}
    result = asyncio.run(
        run_preflight(
            _acct(
                {
                    "/auth/key": (
                        200,
                        {"data": {"limit_remaining": None, "expires_at": "2099-01-01T00:00:00"}},
                    ),
                    "/credits": (500, None),
                }
            ),
            0.30,
        )
    )
    assert any("unlimited" in n or "limit_remaining" in n for n in result.notices)

    result = asyncio.run(
        run_preflight(
            _acct(
                {
                    "/auth/key": (200, {"data": {"expires_at": "garbage"}}),
                    "/credits": (500, None),
                }
            ),
            0.30,
        )
    )
    assert any("could not parse" in n for n in result.notices)

    with pytest.raises(PreflightRefused):
        asyncio.run(run_preflight(_acct({**ok, "/auth/key": (402, None)}), 0.30))

    result = asyncio.run(run_preflight(_acct({**ok, "/auth/key": (500, None)}), 0.30))
    assert any("unexpected key check response" in n for n in result.notices)

    result = asyncio.run(
        run_preflight(
            _acct(
                {
                    **ok,
                    "/credits": (200, {"data": {"total_credits": 0, "total_usage": 0.199}}),
                }
            ),
            0.30,
        )
    )
    assert result.credits == {"total_credits": 0.0, "total_usage": 0.199}

    result = asyncio.run(
        run_preflight(_acct({**ok, "/credits": ConnectionError("down")}), 0.30)
    )
    assert result.credits is None

    result = asyncio.run(
        run_preflight(_acct({**ok, "/auth/key": (200, {"data": {"limit_remaining": 0.30}})}), 0.30)
    )
    assert result.limit_remaining == 0.30
