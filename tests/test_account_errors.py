from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
import typer.main
from typer.testing import CliRunner

from conftest import run_repl
from cora.bench.preflight import PreflightRefused, run_preflight
from cora.cli.main import app
from cora.cli.repl import COMMANDS
from cora.core.errors import (
    DETAIL_MAX_CHARS,
    ProviderAccountError,
    ProviderError,
    account_guidance,
    describe_provider_error,
    trim_detail,
)
from cora.core.providers.openrouter import (
    BALANCE_WARNING,
    CREDITS_URL,
    OpenRouterProvider,
    openrouter_account_status,
)
from cora.core.state import SessionStore
from cora.core.types import CompletionRequest, Message

KEY = "sk-or-v1-SENTINEL-0123456789abcdef"
BODY_402 = json.dumps(
    {
        "error": {
            "code": 402,
            "message": "This request requires more credits, or fewer max_tokens. You requested "
            "up to 1024 tokens, but can only afford 528 tokens. key=" + KEY,
        }
    }
)
BODY = {401: f"unauthorized {KEY}", 402: BODY_402, 403: f"forbidden {KEY}"}

FINAL_BODY = {
    "choices": [{"message": {"content": "Final Answer: 8731"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00001},
    "model": "test/cheap",
}

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
""" + "\n[agent]\napproval = \"auto\"\n"

CASE_LINE = json.dumps(
    {
        "id": "a",
        "expected": "cheap",
        "prompt": "What is 2+2?",
        "tokens": {"input": 1000, "output": 0},
    }
)
REQ = CompletionRequest("test/cheap", [Message("user", "hi")], 16, 0.0)


class Fake:
    def __init__(self) -> None:
        self.key: tuple = (200, {"data": {"limit_remaining": None}})
        self.credits: tuple | BaseException = (
            200,
            {"data": {"total_credits": 5, "total_usage": 0.2}},
        )
        self.chat: tuple = (200, FINAL_BODY)
        self.posts = 0


@pytest.fixture
def fake(monkeypatch) -> Fake:
    state = Fake()

    async def send(client_self, request, **kw):
        if request.method == "GET":
            if request.url.path.endswith("/auth/key"):
                status, body = state.key
            elif request.url.path.endswith("/credits"):
                if isinstance(state.credits, BaseException):
                    raise state.credits
                status, body = state.credits
            else:
                raise AssertionError(f"unexpected GET {request.url}")
        else:
            state.posts += 1
            status, body = state.chat
        if isinstance(body, dict):
            return httpx.Response(status, json=body, headers={"x-echo": KEY}, request=request)
        return httpx.Response(status, text=body, headers={"x-echo": KEY}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return state


@pytest.fixture
def env(monkeypatch, tmp_path, no_network):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CONFIG_TOML, encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    return cfg, ws, tmp_path / "out"


def check_402(text: str) -> None:
    assert "out of credits" in text
    assert CREDITS_URL in text
    assert "buy credits" in text
    assert "auto top-up" in text
    assert "528" in text
    assert "almost exhausted" in text
    assert "HTTP 402: " in text
    assert text.index("out of credits") < text.index("HTTP 402: ")
    assert KEY not in text


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


def test_guidance_402_hint_and_order():
    g = account_guidance(402, BODY_402.replace(KEY, "[REDACTED]"), provider="openrouter")
    check_402(g)
    assert g.splitlines()[0].startswith("OpenRouter account is out of credits")
    assert g.splitlines()[-1].startswith("HTTP 402: ")


@pytest.mark.parametrize(
    "body", ["<html>Payment Required</html>", "", None, "{not json", json.dumps({"error": "x"})]
)
def test_guidance_402_without_pattern(body):
    g = account_guidance(402, body, provider="openrouter")
    assert "out of credits" in g
    assert CREDITS_URL in g
    assert "auto top-up" in g
    assert "HTTP 402" in g
    assert "almost exhausted" not in g


def test_guidance_401_403_distinct():
    g1 = account_guidance(401, "unauthorized", provider="openrouter")
    g3 = account_guidance(403, "forbidden", provider="openrouter")
    assert "invalid, revoked or expired" in g1
    assert "denied access" in g3
    assert "HTTP 401" in g1
    assert "HTTP 403" in g3
    assert g1 != g3
    for g in (g1, g3):
        for word in (CREDITS_URL, "out of credits", "top-up", "almost exhausted"):
            assert word not in g


def test_detail_trimmed():
    g = account_guidance(402, "can only afford 7 tokens " + "y" * 5000, provider="openrouter")
    assert len(g.splitlines()[-1]) <= len("HTTP 402: ") + DETAIL_MAX_CHARS
    assert "y" * 400 not in g
    assert "7 tokens" in g
    assert trim_detail(json.dumps({"error": {"message": "m"}})) == "m"


def test_describe_passthrough():
    assert describe_provider_error(ProviderError("openrouter HTTP 503: x")) == (
        "openrouter HTTP 503: x"
    )
    assert "out of credits" in describe_provider_error(
        ProviderAccountError(402, "x", provider="openrouter")
    )


def test_provider_redacts_and_carries_body(env):
    p = OpenRouterProvider(
        {}, transport=httpx.MockTransport(lambda r: httpx.Response(402, text=BODY_402))
    )
    with pytest.raises(ProviderAccountError) as info:
        asyncio.run(p.complete(REQ))
    exc = info.value
    assert KEY not in exc.body
    assert "[REDACTED]" in exc.body
    check_402(describe_provider_error(exc))

    with pytest.raises(ProviderAccountError) as info:
        asyncio.run(p.stream(REQ, lambda t: None))
    exc = info.value
    assert KEY not in exc.body
    assert "[REDACTED]" in exc.body
    check_402(describe_provider_error(exc))

    sse = b'data: {"error":{"code":402,"message":"can only afford 9 tokens"}}\n\n'
    p_sse = OpenRouterProvider(
        {}, transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sse))
    )
    with pytest.raises(ProviderAccountError) as info:
        asyncio.run(p_sse.stream(REQ, lambda t: None))
    text = describe_provider_error(info.value)
    assert "9 tokens" in text
    assert "out of credits" in text


@pytest.mark.parametrize("status", [401, 402, 403])
@pytest.mark.parametrize("argv", [["run", "hi"], ["-p", "hi"]])
def test_run_and_print_account_errors(env, fake, status, argv):
    cfg, ws, _ = env
    fake.chat = (status, BODY[status])
    r = CliRunner().invoke(app, [*argv, "-c", str(cfg), "-w", str(ws)])
    assert r.exit_code == 2
    assert KEY not in r.output
    if status == 402:
        check_402(r.output)
    elif status == 401:
        assert "invalid, revoked or expired" in r.output
        assert "HTTP 401" in r.output
        assert CREDITS_URL not in r.output
    else:
        assert "denied access" in r.output
        assert "HTTP 403" in r.output
        assert CREDITS_URL not in r.output


def test_run_5xx_unchanged(env, fake):
    cfg, ws, _ = env
    fake.chat = (503, "down")
    r = CliRunner().invoke(app, ["run", "hi", "-c", str(cfg), "-w", str(ws)])
    assert r.exit_code == 2
    assert "openrouter HTTP 503" in r.output
    assert "out of credits" not in r.output


def test_resume_402(env, fake):
    cfg, ws, _ = env
    fake.chat = (402, BODY_402)
    r = CliRunner().invoke(app, ["run", "hi", "-c", str(cfg), "-w", str(ws)])
    assert r.exit_code == 2
    ids = SessionStore(ws / ".cora" / "sessions").list_ids()
    assert len(ids) == 1
    r = CliRunner().invoke(app, ["resume", ids[0], "-c", str(cfg), "-w", str(ws)])
    assert r.exit_code == 2
    check_402(r.output)


def test_repl_402_continues(env, fake):
    cfg, ws, _ = env
    fake.chat = (402, BODY_402)
    out = run_repl(ws, cfg, ["hello", "/status"])
    check_402(out)
    assert "workdir:" in out
    assert out.index("HTTP 402: ") < out.rindex("workdir:")


def test_bench_live_abort_guidance(env, fake):
    cfg, ws, out = env
    fake.chat = (402, BODY_402)
    r = CliRunner().invoke(
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
            "explore_find_port",
            "--out",
            str(out),
        ],
    )
    assert r.exit_code == 3
    assert "live bench aborted" in r.output
    check_402(r.output)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["aborted"].startswith("HTTP 402")
    for path in out.rglob("*"):
        if path.is_file():
            assert KEY not in path.read_text(encoding="utf-8", errors="replace"), path


def test_decider_eval_abort_guidance(env, fake, tmp_path):
    cfg, ws, _ = env
    cases = tmp_path / "c.jsonl"
    cases.write_text(CASE_LINE + "\n", encoding="utf-8")
    fake.chat = (402, BODY_402)
    r = CliRunner().invoke(
        app,
        [
            "decider",
            "eval",
            "--cases",
            str(cases),
            "--decider",
            "llm",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(ws),
        ],
    )
    assert r.exit_code == 3
    assert "decider eval aborted" in r.output
    check_402(r.output)


def _zero_balance_argv(kind: str, cfg: Path, ws: Path, out: Path, tmp_path: Path) -> list[str]:
    if kind == "bench":
        return [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(ws),
            "--protocols",
            "react",
            "--tasks",
            "explore_find_port",
            "--out",
            str(out),
        ]
    if kind == "ab":
        return [
            "bench",
            "--live",
            "--ab",
            "deleg-off",
            "--models",
            "test/cheap",
            "--protocols",
            "react",
            "--tasks",
            "query_client_timeout",
            "-c",
            str(cfg),
            "-w",
            str(ws),
            "--out",
            str(out),
        ]
    cases = tmp_path / "c.jsonl"
    cases.write_text(CASE_LINE + "\n", encoding="utf-8")
    return [
        "decider",
        "eval",
        "--cases",
        str(cases),
        "--decider",
        "llm",
        "--live",
        "-c",
        str(cfg),
        "-w",
        str(ws),
    ]


@pytest.mark.parametrize("kind", ["bench", "ab", "decider"])
def test_preflight_warns_on_zero_balance(env, fake, tmp_path, kind):
    cfg, ws, out = env
    fake.credits = (200, {"data": {"total_credits": 0, "total_usage": 0.199}})
    r = CliRunner().invoke(app, _zero_balance_argv(kind, cfg, ws, out, tmp_path))
    assert r.exit_code == 0
    assert fake.posts >= 1
    assert BALANCE_WARNING in r.output
    assert "HTTP 402" in r.output
    assert CREDITS_URL in r.output
    assert "auto top-up" in r.output
    assert KEY not in r.output

    fake.credits = (200, {"data": {"total_credits": 5, "total_usage": 0.2}})
    r = CliRunner().invoke(app, _zero_balance_argv(kind, cfg, ws, out, tmp_path))
    assert BALANCE_WARNING not in r.output
    assert r.exit_code == 0


@pytest.mark.parametrize(
    "credits",
    [
        (500, "err"),
        (200, "not json"),
        (200, {"data": {"total_credits": 0}}),
        (200, {"data": {}}),
        httpx.ReadTimeout("t"),
        httpx.ConnectError("c"),
    ],
)
def test_credits_failures_silent(env, fake, tmp_path, credits):
    cfg, ws, out = env
    fake.credits = credits
    r = CliRunner().invoke(app, _zero_balance_argv("bench", cfg, ws, out, tmp_path))
    assert r.exit_code == 0
    assert fake.posts >= 1
    assert BALANCE_WARNING not in r.output


def test_credits_timeout_unit():
    result = asyncio.run(
        run_preflight(
            _acct(
                {
                    "/auth/key": (200, {"data": {"limit_remaining": None}}),
                    "/credits": TimeoutError(),
                }
            ),
            0.0,
        )
    )
    assert result.balance is None
    assert not any(BALANCE_WARNING in n for n in result.notices)


def test_preflight_balance_unit():
    zero = asyncio.run(
        run_preflight(
            _acct(
                {
                    "/auth/key": (200, {"data": {"limit_remaining": None}}),
                    "/credits": (200, {"data": {"total_credits": 0, "total_usage": 0.199}}),
                }
            ),
            0.0,
        )
    )
    assert zero.balance == pytest.approx(-0.199)
    warnings = [n for n in zero.notices if BALANCE_WARNING in n]
    assert len(warnings) == 1
    assert CREDITS_URL in warnings[0]
    assert "402" in warnings[0]

    ok = asyncio.run(
        run_preflight(
            _acct(
                {
                    "/auth/key": (200, {"data": {"limit_remaining": None}}),
                    "/credits": (200, {"data": {"total_credits": 5, "total_usage": 0.2}}),
                }
            ),
            0.0,
        )
    )
    assert ok.balance == pytest.approx(4.8)
    assert not any(BALANCE_WARNING in n for n in ok.notices)


def test_key_limit_is_not_balance():
    routes = {
        "/auth/key": (200, {"data": {"limit_remaining": 0}}),
        "/credits": (200, {"data": {"total_credits": 5, "total_usage": 0.2}}),
    }
    result = asyncio.run(run_preflight(_acct(routes), 0.0))
    assert not any(BALANCE_WARNING in n for n in result.notices)
    assert any("key spending cap, not the account balance" in n for n in result.notices)
    with pytest.raises(PreflightRefused) as info:
        asyncio.run(run_preflight(_acct(routes), 0.30))
    assert "not the account balance" in str(info.value)
    assert BALANCE_WARNING not in str(info.value)


def test_status_no_network(no_network, cfg_file, ws):
    out = run_repl(ws, cfg_file, ["/status"])
    assert "workdir:" in out


def test_no_new_commands():
    assert "/credits" not in COMMANDS
    assert "credits" not in typer.main.get_command(app).commands


def test_usage_documents_account_errors():
    text = (Path(__file__).resolve().parents[1] / "USAGE.md").read_text(encoding="utf-8")
    for needle in (
        CREDITS_URL,
        "auto top-up",
        "total_credits - total_usage",
        "HTTP 401",
        "402",
        "403",
    ):
        assert needle in text
    row = next(line for line in text.splitlines() if line.startswith("| 2 |"))
    assert "HTTP 401, 402, 403" in row
