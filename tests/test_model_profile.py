from __future__ import annotations

import asyncio
import dataclasses
import itertools
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, ScriptedProvider, act
from cora.cli.main import app
from cora.core.agent import Agent, RunResult
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.config import (
    CoraConfig,
    ModelOverride,
    ModelSpec,
    apply_model_override,
    apply_pin,
    check_decider_model,
    find_model,
    load_config,
    parse_config,
)
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter, estimate_cost, format_summary
from cora.core.observability import read_events
from cora.core.outcome import OUTCOME_KEYS, outcome_dict
from cora.core.providers import register_provider
from cora.core.router import HeuristicRouter
from cora.core.state import Session, SessionStore, StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionRequest, CompletionResponse

ROOT = Path(__file__).resolve().parents[1]


@register_provider("m7_fake_a")
class FakeA(ScriptedProvider):
    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return dataclasses.replace(
            await super().complete(req), input_tokens=1000, output_tokens=100
        )


@register_provider("m7_fake_b")
class FakeB(ScriptedProvider):
    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return dataclasses.replace(
            await super().complete(req), input_tokens=1000, output_tokens=100
        )


@register_provider("m7_fake_paid")
class FakePaid(ScriptedProvider):
    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        return dataclasses.replace(
            await super().complete(req),
            input_tokens=1000,
            output_tokens=100,
            cost_usd=0.0042,
        )


TWO = {
    "models": [
        {
            "id": "vendor/m",
            "provider": "m7_fake_a",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 2.0,
        },
        {
            "id": "vendor/m",
            "provider": "m7_fake_b",
            "tier": "strong",
            "input_usd_per_mtok": 3.0,
            "output_usd_per_mtok": 4.0,
        },
    ],
    "agent": {"approval": "auto"},
}


def _clock():
    counter = itertools.count(0.0, 0.5)
    return lambda: next(counter)


def _mock_cfg(provider: str) -> CoraConfig:
    return parse_config(
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
                    "provider": provider,
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def test_same_id_two_providers_priced_separately(scripted, ws):
    cfg = parse_config(TWO)
    a, b = cfg.models
    meter = CostMeter()
    rec_a = meter.record(a, "cheap", "react", 1000, 100)
    rec_b = meter.record(b, "strong", "react", 1000, 100)
    assert rec_a.cost_usd == pytest.approx(0.0012)
    assert rec_b.cost_usd == pytest.approx(0.0034)
    assert rec_a.provider == "m7_fake_a"
    assert rec_b.provider == "m7_fake_b"
    assert rec_a.cost_source == "catalog:vendor/m@m7_fake_a"
    assert rec_b.cost_source == "catalog:vendor/m@m7_fake_b"

    scripted.script[:] = ["Final Answer: ok"]
    pinned_b = apply_pin(cfg, "vendor/m@m7_fake_b")
    r = asyncio.run(Agent(pinned_b, ws, ApprovalPolicy("auto")).run("q"))
    group = r.summary["by_model_provider"]["vendor/m@m7_fake_b"]
    assert group["cost_usd"] == pytest.approx(group["calls"] * 0.0034)

    scripted.script[:] = ["Final Answer: ok"]
    r = asyncio.run(Agent(apply_pin(cfg, "vendor/m"), ws, ApprovalPolicy("auto")).run("q"))
    group = r.summary["by_model_provider"]["vendor/m@m7_fake_a"]
    assert group["cost_usd"] == pytest.approx(group["calls"] * 0.0012)


def test_duplicate_pair_rejected(tmp_path):
    with pytest.raises(ConfigError, match="duplicate"):
        parse_config({"models": [dict(TWO["models"][0]), dict(TWO["models"][0])]})

    ws = tmp_path / "ws"
    ws.mkdir()
    path = tmp_path / "cora.toml"
    path.write_text(
        CFG_TOML
        + '\n[[models]]\nid = "mock/cheap"\nprovider = "scripted"\ntier = "cheap"\n'
        + "input_usd_per_mtok = 1.0\noutput_usd_per_mtok = 2.0\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app, ["run", "q", "--headless", "--json", "-w", str(ws), "-c", str(path)]
    )
    assert result.exit_code == 2


def test_model_refs_resolve():
    cfg = parse_config(TWO)
    models = cfg.models
    assert find_model(models, "vendor/m@m7_fake_b").provider == "m7_fake_b"
    assert find_model(models, "vendor/m").provider == "m7_fake_a"
    assert find_model(models, "vendor/m@nope") is None
    assert HeuristicRouter(cfg).resolve("vendor/m@m7_fake_b").provider == "m7_fake_b"

    with pytest.raises(ConfigError, match="not in the current model configuration"):
        apply_pin(cfg, "vendor/m@nope")
    with pytest.raises(ConfigError, match="not in the current model configuration"):
        apply_model_override(cfg, ModelOverride("cheap", "vendor/m@nope"), "flag")

    overridden = apply_model_override(
        cfg, ModelOverride("cheap", "vendor/m@m7_fake_b"), "flag"
    ).models[0]
    assert overridden.id == "vendor/m"
    assert overridden.provider == "m7_fake_b"
    assert overridden.input_usd_per_mtok == 3.0
    assert overridden.output_usd_per_mtok == 4.0

    check_decider_model("vendor/m@m7_fake_b", models)
    with pytest.raises(ConfigError):
        check_decider_model("vendor/m@nope", models)


def test_cost_model_parsing():
    base = TWO["models"][0]
    plain = parse_config({"models": [base], "agent": {"approval": "auto"}})
    assert plain.models[0].cost_model == "catalog"
    self_hosted = {**base, "cost_model": "self_hosted"}
    cfg = parse_config({"models": [self_hosted], "agent": {"approval": "auto"}})
    assert cfg.models[0].cost_model == "self_hosted"
    with pytest.raises(ConfigError, match="cost_model"):
        parse_config({"models": [{**base, "cost_model": "gpu"}], "agent": {"approval": "auto"}})


def test_four_cost_sources(scripted, mock_config, ws):
    spec = ModelSpec("vendor/m", "m7_fake_a", "cheap", 1.0, 2.0)
    meter = CostMeter()
    provider_rec = meter.record(spec, "cheap", "react", 1000, 100, cost_usd=0.5, latency_s=0.25)
    catalog_rec = meter.record(spec, "cheap", "react", 1000, 100, latency_s=0.25)
    self_spec = dataclasses.replace(spec, cost_model="self_hosted")
    self_rec = meter.record(self_spec, "cheap", "react", 1000, 100, latency_s=0.25)
    unknown = ModelSpec("u", "p", "cheap", None, None)
    unpriced_rec = meter.record(unknown, "cheap", "react", 1000, 100, latency_s=0.25)

    assert provider_rec.cost_source == "provider_usage"
    assert catalog_rec.cost_source == "catalog:vendor/m@m7_fake_a"
    assert self_rec.cost_source == "self_hosted"
    assert unpriced_rec.cost_source == "unpriced"
    assert unknown.price_known is False
    for rec in (provider_rec, catalog_rec, self_rec, unpriced_rec):
        assert rec.provider
        assert rec.latency_s == 0.25

    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    r = asyncio.run(Agent(mock_config, ws, ApprovalPolicy("auto")).run("q"))
    for rec in r.session.meter:
        assert rec["provider"] == "scripted"
        assert rec["cost_source"]
        assert rec["latency_s"] is not None
    events = [e for e in read_events(r.log_path) if e["type"] == "llm_call"]
    assert events
    for e in events:
        assert "provider" in e
        assert "latency_s" in e

    scripted.script[:] = ["Final Answer: ok"]
    paid = asyncio.run(Agent(_mock_cfg("m7_fake_paid"), ws, ApprovalPolicy("auto")).run("q"))
    assert paid.session.meter[0]["cost_source"] == "provider_usage"
    assert paid.session.meter[0]["cost_usd"] == pytest.approx(0.0042)


def test_summary_groups_and_p50(scripted, mock_config, ws):
    meter = CostMeter()
    a, b = parse_config(TWO).models
    for lat in (0.1, 0.3, 0.2):
        meter.record(a, "cheap", "react", 1000, 100, latency_s=lat)
    meter.record(b, "strong", "react", 1000, 100, latency_s=1.0)
    groups = meter.summary()["by_model_provider"]
    assert groups["vendor/m@m7_fake_a"]["p50_latency_s"] == pytest.approx(0.2)
    assert groups["vendor/m@m7_fake_b"]["p50_latency_s"] == pytest.approx(1.0)
    assert groups["vendor/m@m7_fake_a"]["latency_calls"] == 3
    assert groups["vendor/m@m7_fake_b"]["latency_calls"] == 1
    text = format_summary(meter.summary())
    assert "profile vendor/m@m7_fake_a: calls=3" in text
    assert "p50_latency_s=0.200" in text
    assert "cost_source=catalog:vendor/m@m7_fake_a" in text

    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    agent = Agent(mock_config, ws, ApprovalPolicy("auto"))
    agent.clock = _clock()
    r = asyncio.run(agent.run("q"))
    d = outcome_dict(r, None, wall_s=0.0)
    assert set(d) == set(OUTCOME_KEYS)
    [profile] = d["profile"]
    assert profile["model"] == "mock/cheap"
    assert profile["provider"] == "scripted"
    assert profile["p50_latency_s"] == 0.5
    assert profile["cost_source"] == "catalog:mock/cheap@scripted"
    assert profile["excluded_from_cost_usd"] is False
    assert d["cost_usd"] == r.summary["total_cost_usd"]
    assert d["models"] == ["mock/cheap"]


def test_self_hosted_mixed_excluded(tmp_path, scripted, ws):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "local/llama",
                    "provider": "m7_fake_a",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "cost_model": "self_hosted",
                },
                {
                    "id": "vendor/x",
                    "provider": "m7_fake_b",
                    "tier": "strong",
                    "input_usd_per_mtok": 3.0,
                    "output_usd_per_mtok": 4.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )
    a, b = cfg.models
    meter = CostMeter()
    meter.record(a, "cheap", "react", 1000, 100)
    meter.record(b, "strong", "react", 1000, 100)
    assert meter.total_cost_usd == pytest.approx(0.0034)
    assert meter.self_hosted_cost_usd == pytest.approx(0.0012)
    summary = meter.summary()
    assert summary["self_hosted"]["calls"] == 1
    text = format_summary(summary)
    for needle in (
        "total_estimated_cost_usd: 0.003400",
        "self_hosted_cost_usd: 0.001200",
        "excluded from total_estimated_cost_usd",
        "[self_hosted: excluded from total]",
    ):
        assert needle in text

    result = RunResult(
        Session(id="s", task="t"),
        "ok",
        StopReason.FINAL_ANSWER,
        meter.summary(),
        tmp_path / "e.jsonl",
    )
    outcome = outcome_dict(result, None, wall_s=0.0)
    assert outcome["cost_usd"] == pytest.approx(0.0034)
    self_entries = [p for p in outcome["profile"] if p["excluded_from_cost_usd"]]
    assert len(self_entries) == 1
    assert self_entries[0]["excluded_from_cost_usd"] is True

    def _governed(cost_model: str) -> CoraConfig:
        return parse_config(
            {
                "models": [
                    {
                        "id": "local/a",
                        "provider": "scripted",
                        "tier": "cheap",
                        "input_usd_per_mtok": 1.0,
                        "output_usd_per_mtok": 2.0,
                        "cost_model": cost_model,
                    },
                    {
                        "id": "local/b",
                        "provider": "scripted",
                        "tier": "strong",
                        "input_usd_per_mtok": 3.0,
                        "output_usd_per_mtok": 4.0,
                        "cost_model": cost_model,
                    },
                ],
                "agent": {"approval": "auto"},
            }
        )

    scripted.script[:] = ["Final Answer: ok"]
    gov = BudgetGovernor(BudgetLimits(cost_usd=1e-9), project_cost=True)
    r = asyncio.run(
        Agent(_governed("self_hosted"), ws, ApprovalPolicy("auto"), governor=gov).run("q")
    )
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert gov.tripped is None

    scripted.script[:] = ["Final Answer: ok"]
    gov = BudgetGovernor(BudgetLimits(cost_usd=1e-9), project_cost=True)
    r = asyncio.run(
        Agent(_governed("catalog"), ws, ApprovalPolicy("auto"), governor=gov).run("q")
    )
    assert r.stop_reason == StopReason.COST_LIMIT


def test_plain_config_unchanged(scripted, mock_config, ws):
    cfg = load_config(ROOT / "cora.toml")
    for m in cfg.models:
        assert m.cost_model == "catalog"
        assert find_model(cfg.models, m.id) is m

    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    r = asyncio.run(Agent(mock_config, ws, ApprovalPolicy("auto")).run("q"))
    assert r.session.model_id == "mock/cheap"
    assert set(r.summary) >= {
        "calls",
        "by_model",
        "total_cost_usd",
        "unknown_cost_calls",
        "provider_cost_calls",
        "delegated",
    }
    assert list(r.summary["by_model"]) == ["mock/cheap"]
    spec = mock_config.models[0]
    assert r.summary["total_cost_usd"] == pytest.approx(
        sum(
            estimate_cost(spec, rec["input_tokens"], rec["output_tokens"])
            for rec in r.session.meter
        )
    )
    assert r.summary["provider_cost_calls"] == 0
    assert r.summary["unknown_cost_calls"] == 0
    assert "profile " not in format_summary(r.summary)


def test_legacy_session_resumes(scripted, mock_config, ws):
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")

    def crash(req):
        raise RuntimeError("simulated crash")

    scripted.script[:] = [act("list_files", {}), act("read_file", {"path": "a.txt"}), crash]
    agent = Agent(mock_config, ws, ApprovalPolicy("auto"))
    with pytest.raises(RuntimeError):
        asyncio.run(agent.run("inspect a.txt"))

    store = SessionStore(ws / ".cora" / "sessions")
    sid = store.list_ids()[0]
    saved = store.load(sid)
    for rec in saved.meter:
        rec.pop("provider", None)
        rec.pop("latency_s", None)
        rec["cost_source"] = "price"
    store.save(saved)

    scripted.script[:] = ["Final Answer: ok"]
    resumed = asyncio.run(Agent(mock_config, ws, ApprovalPolicy("auto")).resume(sid))
    assert resumed.answer == "ok"
    groups = resumed.summary["by_model_provider"]
    legacy = groups["mock/cheap@unknown"]
    assert legacy["latency_calls"] == 0
    assert legacy["p50_latency_s"] is None
    assert legacy["cost_source"] == "legacy"
    assert groups["mock/cheap@scripted"]["p50_latency_s"] is not None
    text = format_summary(resumed.summary)
    assert "profile mock/cheap@unknown" in text
    assert "p50_latency_s=n/a" in text

    legacy_row = {
        "ts": "2026-01-01T00:00:00+00:00",
        "model": "mock/cheap",
        "tier": "cheap",
        "purpose": "react",
        "input_tokens": 1000,
        "output_tokens": 100,
        "cost_usd": 0.0012,
    }
    meter = CostMeter.from_list(
        [
            {**legacy_row, "cost_source": "provider", "future_key": 1},
            {**legacy_row, "cost_source": "unknown"},
            {**legacy_row},
        ]
    )
    assert [rec.cost_source for rec in meter.records] == ["provider_usage", "unpriced", "legacy"]


def test_no_secret_in_profile_outputs(monkeypatch, scripted, mock_config, ws):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-M7DUMMYSECRET")
    scripted.script[:] = [act("list_files", {}), "Final Answer: ok"]
    r = asyncio.run(Agent(mock_config, ws, ApprovalPolicy("auto")).run("q"))
    blob = "\n".join(
        [
            format_summary(r.summary),
            json.dumps(outcome_dict(r, None, wall_s=0.0)),
            json.dumps(r.session.meter),
            r.log_path.read_text(encoding="utf-8"),
        ]
    )
    assert "M7DUMMYSECRET" not in blob


def test_bench_compare_names_cost_source(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "task": "t1",
                        "model": "mock/cheap",
                        "protocol": "react",
                        "status": "solved",
                        "cost_usd": 0.01,
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "latency_s": 1.0,
                        "arm": None,
                    }
                ],
                "partial": False,
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["bench", "compare", str(report)])
    assert result.exit_code == 0, result.output
    assert "cost_source:" in result.stdout
