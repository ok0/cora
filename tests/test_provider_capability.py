from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from conftest import run_repl, with_decider
from cora.bench.decider_eval import load_cases, run_decider_eval
from cora.bench.live import _preflight
from cora.bench.preflight import PreflightRefused, run_preflight
from cora.cli.main import app
from cora.core.errors import ProviderAccountError, describe_provider_error
from cora.core.providers import AccountStatus, register_account_guidance, register_provider
from cora.core.providers.openrouter import openrouter_account_status

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-fake-SENTINEL-0123456789abcdef"
ABORT_402 = "HTTP 402 from the provider (insufficient credits)"
FAKE_GUIDANCE = "AcctFake says: top up the acctfake wallet."
CASE_LINE = json.dumps(
    {
        "id": "a",
        "expected": "cheap",
        "prompt": "What is 2+2?",
        "tokens": {"input": 1000, "output": 0},
    }
)
DENY_TOML = """
[providers.denyfake]
api_key_env = "DENYFAKE_API_KEY"

[[models]]
id = "deny/cheap"
provider = "denyfake"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0
supports_tools = true

[[models]]
id = "deny/strong"
provider = "denyfake"
tier = "strong"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[bench]
models = ["deny/cheap"]

[agent]
approval = "auto"
"""


@register_account_guidance("acctfake")
def _fake_guidance(status: int, body: str) -> list[str]:
    return [f"{FAKE_GUIDANCE} ({status})"]


class Capable:
    display_name = "AcctFake"

    def __init__(self, status=None, exc=None, delay=0.0):
        self.status, self.exc, self.delay, self.calls = status, exc, delay, 0

    async def account_status(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return self.status


class Plain:
    async def complete(self, req):
        raise AssertionError("not called")


class Pool:
    def __init__(self, items):
        self.items = items

    def get(self, name):
        return self.items[name]


@register_provider("denyfake")
class DenyProvider:
    def __init__(self, settings):
        self._key = os.environ.get(str(settings.get("api_key_env", "")), "")

    async def complete(self, req):
        body = f"insufficient funds key={self._key}"
        if self._key:
            body = body.replace(self._key, "[REDACTED]")
        raise ProviderAccountError(
            402, "denyfake HTTP 402: insufficient funds", body=body, provider="denyfake"
        )


def pf(targets, cap=0.30, **kw):
    return asyncio.run(run_preflight(targets, cap, **kw))


def _or(routes: dict):
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


@pytest.fixture
def deny_env(monkeypatch, tmp_path, no_network):
    monkeypatch.setenv("DENYFAKE_API_KEY", KEY)
    cfg = tmp_path / "cora.toml"
    cfg.write_text(DENY_TOML, encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    return cfg, ws, tmp_path / "out"


def test_ac1_zero_balance_warns():
    result = pf({"acctfake": Capable(AccountStatus(provider="AcctFake", balance=0.0))})
    warnings = [n for n in result.notices if "WARNING" in n]
    assert len(warnings) == 1
    assert "AcctFake" in warnings[0]
    assert "openrouter" not in warnings[0].lower()


def test_ac2_positive_balance_no_warning():
    result = pf({"acctfake": Capable(AccountStatus(provider="AcctFake", balance=5.0))})
    assert not any("WARNING" in n for n in result.notices)
    assert result.balance == 5.0


def test_ac3_non_capable_skips():
    assert pf({"plainfake": Plain()}).notices == [
        "preflight: account check not available for plainfake: skipped"
    ]
    assert pf({"nonefake": Capable(None)}).notices == [
        "preflight: account check not available for nonefake: skipped"
    ]


def test_ac4_failures_do_not_propagate():
    result = pf({"acctfake": Capable(exc=RuntimeError(f"boom {KEY}"))})
    assert result.notices == [
        "preflight: account check for acctfake failed (RuntimeError); continuing"
    ]

    result = pf(
        {"acctfake": Capable(AccountStatus(provider="AcctFake"), delay=5.0)}, timeout_s=0.05
    )
    assert len(result.notices) == 1
    assert result.notices[0].startswith("preflight: account check for acctfake timed out")
    assert result.notices[0].endswith("; continuing")

    result = pf({"acctfake": Capable({"balance": 0})})
    assert result.notices == [
        "preflight: account check for acctfake failed (unexpected result); continuing"
    ]

    pf({"acctfake": Capable(AccountStatus(provider="AcctFake", balance="x"))})

    all_notices = []
    for target in (
        Capable(exc=RuntimeError(f"boom {KEY}")),
        Capable({"balance": 0}),
    ):
        all_notices.extend(pf({"acctfake": target}).notices)
    assert all(KEY not in n for n in all_notices)


def test_ac5_mixed_and_unused():
    cap = Capable(AccountStatus(provider="AcctFake", balance=1.0))
    unused = Capable(AccountStatus(provider="Unused", balance=0.0))
    pool = Pool({"acctfake": cap, "plainfake": Plain(), "unusedfake": unused})
    used = [
        SimpleNamespace(provider="acctfake"),
        SimpleNamespace(provider="plainfake"),
        SimpleNamespace(provider="acctfake"),
    ]
    notes: list[str] = []
    asyncio.run(_preflight(pool, used, None, 0.30, notes.append))
    assert cap.calls == 1
    assert unused.calls == 0
    assert "preflight: account check not available for plainfake: skipped" in notes
    assert not any("unusedfake" in n or "acctfake: skipped" in n for n in notes)
    assert not any("Unused" in n for n in notes)


def test_ac6_no_openrouter_branch_in_neutral_code():
    for rel in ("src/cora/bench/preflight.py", "src/cora/bench/live.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert '"openrouter"' not in text
        assert "'openrouter'" not in text
    preflight_text = (ROOT / "src/cora/bench/preflight.py").read_text(encoding="utf-8")
    assert "openrouter" not in preflight_text.lower()


@pytest.mark.parametrize("s", [401, 402, 403])
def test_ac7_refusal_uses_provider_guidance(s):
    exc = ProviderAccountError(
        s, f"denied {KEY}", body=f"denied {KEY}", provider="acctfake"
    )
    with pytest.raises(PreflightRefused) as info:
        pf({"acctfake": Capable(exc=exc)})
    message = str(info.value)
    assert f"{FAKE_GUIDANCE} ({s})" in message
    assert f"HTTP {s}" in message
    assert "AcctFake refused the key check" in message
    assert KEY not in message
    assert "openrouter" not in message.lower()


def test_ac8_limit_remaining_below_cap_refuses():
    with pytest.raises(PreflightRefused) as info:
        pf({"acctfake": Capable(AccountStatus(provider="AcctFake", limit_remaining=0.05))})
    assert "below this run's cap" in str(info.value)

    result = pf({"acctfake": Capable(AccountStatus(provider="AcctFake", limit_remaining=1.0))})
    assert result.limit_remaining == 1.0

    expired = AccountStatus(
        provider="AcctFake", expires_at=datetime(2020, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(PreflightRefused) as info:
        pf({"acctfake": Capable(expired)})
    assert "expired" in str(info.value)


@pytest.mark.parametrize("s", [401, 402, 403])
def test_ac9_fallback_guidance(s):
    text = describe_provider_error(
        ProviderAccountError(s, f"x {KEY}", body="nope [REDACTED]", provider="nofake")
    )
    assert "nofake" in text
    assert f"HTTP {s}" in text
    lowered = text.lower()
    for word in ("openrouter", "openrouter.ai", ":free"):
        assert word not in lowered
    assert KEY not in text

    bare = describe_provider_error(ProviderAccountError(s, f"x {KEY}", body="nope [REDACTED]"))
    assert "the provider" in bare
    assert f"HTTP {s}" in bare
    assert "openrouter" not in bare.lower()
    assert KEY not in bare


def test_ac10_openrouter_bytes_identical():
    assert describe_provider_error(
        ProviderAccountError(402, "x", body="", provider="openrouter")
    ) == (
        "OpenRouter account is out of credits: the prepaid account balance cannot pay for "
        "this request. This is the account balance, not the API key's limit.\n"
        "Fix: buy credits or enable auto top-up at https://openrouter.ai/settings/credits. "
        "Having a saved payment card alone does not pay for requests.\n"
        "HTTP 402"
    )
    with pytest.raises(PreflightRefused) as info:
        pf(_or({"/auth/key": (401, None), "/credits": (500, None)}))
    assert str(info.value) == (
        "preflight: OpenRouter refused the key check (HTTP 401); not starting the live bench\n"
        "OpenRouter rejected the API key: it is invalid, revoked or expired.\n"
        "Fix: set a valid key in the configured api_key_env (default OPENROUTER_API_KEY).\n"
        "HTTP 401"
    )
    notices = pf(
        _or(
            {
                "/auth/key": (200, {"data": {"limit_remaining": None}}),
                "/credits": (200, {"data": {"total_credits": 0, "total_usage": 0.199}}),
            }
        ),
        0.0,
    ).notices
    assert notices == [
        "preflight: key limit_remaining=unlimited (key spending cap, not the account balance); "
        "run cap $0.0000",
        "preflight: account balance $-0.1990 (total_credits $0.0000 - total_usage $0.1990)",
        "preflight: WARNING: OpenRouter account balance is $-0.1990 (<= 0): requests to paid "
        "models will likely be rejected with HTTP 402 (out of credits). Buy credits or enable "
        "auto top-up at https://openrouter.ai/settings/credits. Continuing anyway (':free' "
        "models can still work).",
    ]


def test_ac11_bench_abort_non_openrouter(deny_env):
    cfg, ws, out = deny_env
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
    assert ABORT_402 in r.output
    assert "preflight: account check not available for denyfake: skipped" in r.output
    assert "Account error from denyfake (HTTP 402)" in r.output
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["aborted"] == ABORT_402
    assert KEY not in r.output
    for path in out.rglob("*"):
        if path.is_file():
            assert KEY not in path.read_text(encoding="utf-8", errors="replace"), path


def test_ac11_run_and_repl_non_openrouter(deny_env):
    cfg, ws, _ = deny_env
    r = CliRunner().invoke(app, ["run", "hi", "-c", str(cfg), "-w", str(ws)])
    assert r.exit_code == 2
    assert "denyfake" in r.output
    assert "HTTP 402" in r.output
    assert KEY not in r.output
    out = run_repl(ws, cfg, ["hello", "/status"])
    assert "denyfake" in out
    assert "HTTP 402" in out
    assert "workdir:" in out


def test_ac11_decider_eval_non_openrouter(mock_config, tmp_path):
    cases = tmp_path / "c.jsonl"
    cases.write_text(CASE_LINE + "\n", encoding="utf-8")
    report = asyncio.run(
        run_decider_eval(
            with_decider(mock_config, kind="llm"),
            load_cases(cases),
            "llm",
            providers=Pool({"scripted": DenyProvider({})}),
            max_cost_usd=0.05,
        )
    )
    assert report.aborted == ABORT_402
    assert "denyfake" in report.abort_guidance
    assert "openrouter" not in report.abort_guidance.lower()


def test_ac14_docs():
    usage = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    assert "account check not available for" in usage
    assert "account_status" in usage
    arch = (ROOT / ".docs" / "architecture.md").read_text(encoding="utf-8")
    for needle in ("account_status", "AccountStatus", "register_account_guidance", "display_name"):
        assert needle in arch
