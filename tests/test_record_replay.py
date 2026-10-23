from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import tomllib

import pytest

from conftest import CFG_TOML, FIXED_CFG_TOML, ScriptedProvider, act
from cora.core.agent import Agent
from cora.core.config import ModelSpec, parse_config
from cora.core.errors import ReplayMissError
from cora.core.metering import CostMeter
from cora.core.providers import register_provider
from cora.core.providers.recording import RecordingProvider
from cora.core.tools.base import ApprovalPolicy
from cora.core.types import CompletionRequest, Message
from record_util import comparable, entries, record_env, seed_ws
from test_headless import base, doc, events, run_cli, write_cfg

SCRIPT = [act("read_file", {"path": "hello.txt"}), "Final Answer: done"]

GEMINI_TOML = (
    CFG_TOML.replace('provider = "scripted"', 'provider = "gemini"')
    + """
[providers.gemini]
type = "openai_compat"
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
api_key_env = "GEMINI_API_KEY"
"""
)

FREE_TOML = """
[[models]]
id = "mock/cheap"
provider = "scripted"
tier = "cheap"
input_usd_per_mtok = 0.0
output_usd_per_mtok = 0.0
free_tier = true

[[models]]
id = "mock/strong"
provider = "scripted"
tier = "strong"
input_usd_per_mtok = 0.0
output_usd_per_mtok = 0.0
free_tier = true
"""

STREAM_TOML = CFG_TOML.replace('provider = "scripted"', 'provider = "scripted_stream"')


def _blocked_init(self, settings) -> None:
    raise AssertionError("provider constructed in replay")


def _cfg(text: str):
    return parse_config(tomllib.loads(text))


def _strip_provider(d: dict) -> dict:
    out = comparable(d)
    out.pop("models", None)
    for p in out["profile"]:
        p.pop("provider", None)
        p["cost_source"] = re.sub(r"@\w+$", "", p["cost_source"])
    return out


def test_headless_record_then_replay_equal(scripted, tmp_path, monkeypatch, no_network):
    cfg = write_cfg(tmp_path, CFG_TOML)
    rec = tmp_path / "rec"
    ws_a = seed_ws(tmp_path / "a")
    scripted.script.extend(SCRIPT)
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_result = run_cli(["run", "q", "--headless", "--json", *base(ws_a, cfg)])
    rec_doc = doc(rec_result)
    assert rec_result.exit_code == 0
    assert len(entries(rec)) == 2

    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    rep_result = run_cli(["run", "q", "--headless", "--json", *base(ws_b, cfg)])
    rep_doc = doc(rep_result)
    assert rep_result.exit_code == 0
    assert comparable(rec_doc) == comparable(rep_doc)
    assert rep_doc["profile"]
    assert all(p["cost_source"].endswith("+replay") for p in rep_doc["profile"])
    llm = [e for e in events(ws_b, rep_doc["session_id"]) if e["type"] == "llm_call"]
    assert llm
    assert all(e["cost_source"].endswith("+replay") for e in llm)


def test_agent_streaming_record_replay(scripted, tmp_path, monkeypatch, no_network):
    cfg = _cfg(STREAM_TOML)
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_deltas: list[str] = []
    rec_run = asyncio.run(
        Agent(cfg, ws_a, ApprovalPolicy("auto"), on_answer_delta=rec_deltas.append).run("q")
    )
    assert "done" in "".join(rec_deltas)

    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    ws_b = seed_ws(tmp_path / "b")
    deltas: list[str] = []
    streamed = asyncio.run(
        Agent(cfg, ws_b, ApprovalPolicy("auto"), on_answer_delta=deltas.append).run("q")
    )
    assert "done" in "".join(deltas)
    ws_c = seed_ws(tmp_path / "c")
    complete = asyncio.run(Agent(cfg, ws_c, ApprovalPolicy("auto")).run("q"))
    for r in (streamed, complete):
        assert r.answer == rec_run.answer
        assert r.stop_reason == rec_run.stop_reason
        assert r.session.total_iterations == rec_run.session.total_iterations
    recorded = [json.loads(p.read_text(encoding="utf-8")) for p in entries(rec)]
    assert recorded and all(e["stream"] is True for e in recorded)


def test_nonstream_recording_replays_on_stream_path(scripted, tmp_path, monkeypatch, no_network):
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_run = asyncio.run(Agent(_cfg(CFG_TOML), ws_a, ApprovalPolicy("auto")).run("q"))

    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    ws_b = seed_ws(tmp_path / "b")
    deltas: list[str] = []
    rep = asyncio.run(
        Agent(_cfg(STREAM_TOML), ws_b, ApprovalPolicy("auto"), on_answer_delta=deltas.append).run(
            "q"
        )
    )
    assert rep.answer == rec_run.answer
    assert "".join(deltas)


def test_replay_miss_exit_2(scripted, tmp_path, monkeypatch, no_network):
    cfg = write_cfg(tmp_path, CFG_TOML)
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    assert run_cli(["run", "q1", "--headless", "--json", *base(ws_a, cfg)]).exit_code == 0

    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    result = run_cli(["run", "q2", "--headless", "--json", *base(ws_b, cfg)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["stop_reason"] == "error"
    err = d["errors"][0]
    assert "replay miss" in err
    assert "mock/cheap" in err
    assert re.search(r"[0-9a-f]{64}", err)

    req = CompletionRequest("mock/cheap", [Message("user", "x")])
    provider = RecordingProvider(None, name="scripted", store_dir=tmp_path / "empty", mode="replay")
    with pytest.raises(ReplayMissError) as exc:
        asyncio.run(provider.complete(req))
    assert re.fullmatch(r"[0-9a-f]{64}", exc.value.key)
    assert exc.value.model == req.model


def test_replay_needs_no_key(scripted, tmp_path, monkeypatch, no_network):
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    cfg_plain = write_cfg(tmp_path, CFG_TOML)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_doc = doc(run_cli(["run", "q", "--headless", "--json", *base(ws_a, cfg_plain)]))

    cfg_gemini = write_cfg(tmp_path, GEMINI_TOML, name="gemini.toml")
    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    result = run_cli(["run", "q", "--headless", "--json", *base(ws_b, cfg_gemini)])
    rep_doc = doc(result)
    assert result.exit_code == 0
    assert _strip_provider(rec_doc) == _strip_provider(rep_doc)


def test_replay_free_tier_cost_zero(scripted, tmp_path, monkeypatch, no_network):
    cfg = write_cfg(tmp_path, FREE_TOML)
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_doc = doc(run_cli(["run", "q", "--headless", "--json", *base(ws_a, cfg)]))
    assert rec_doc["cost_usd"] == 0

    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    rep_doc = doc(run_cli(["run", "q", "--headless", "--json", *base(ws_b, cfg)]))
    assert rep_doc["cost_usd"] == 0
    assert rep_doc["profile"]
    assert all(p["cost_source"] == "free_tier+replay" for p in rep_doc["profile"])


def test_replay_priced_entry_cost(scripted, tmp_path, monkeypatch, no_network):
    @register_provider("priced_fake")
    class PricedFake(ScriptedProvider):
        async def complete(self, req):
            resp = await super().complete(req)
            return dataclasses.replace(resp, cost_usd=0.0123)

    cfg = write_cfg(tmp_path, CFG_TOML.replace('provider = "scripted"', 'provider = "priced_fake"'))
    rec = tmp_path / "rec"
    scripted.script.extend(SCRIPT)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_doc = doc(run_cli(["run", "q", "--headless", "--json", *base(ws_a, cfg)]))

    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    rep_doc = doc(run_cli(["run", "q", "--headless", "--json", *base(ws_b, cfg)]))
    assert rep_doc["cost_usd"] == pytest.approx(rec_doc["cost_usd"])
    assert rep_doc["cost_usd"] > 0
    assert all(p["cost_source"] == "provider_usage+replay" for p in rep_doc["profile"])


def test_governor_cap_trips_on_replay(scripted, tmp_path, monkeypatch, no_network):
    cfg = write_cfg(tmp_path, FIXED_CFG_TOML)
    rec = tmp_path / "rec"
    scripted.script.extend([act("read_file", {"path": "hello.txt"})] * 20)
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_result = run_cli(
        ["run", "q", "--headless", "--json", *base(ws_a, cfg), "--max-cost", "0.005"]
    )
    rec_doc = doc(rec_result)
    assert rec_result.exit_code == 4
    assert rec_doc["stop_reason"] == "budget_exceeded"
    assert rec_doc["budget"]["tripped"] == "cost"

    ws_b = seed_ws(tmp_path / "b")
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    rep_result = run_cli(
        ["run", "q", "--headless", "--json", *base(ws_b, cfg), "--max-cost", "0.005"]
    )
    rep_doc = doc(rep_result)
    assert rep_result.exit_code == 4
    assert rep_doc["stop_reason"] == "budget_exceeded"
    assert rep_doc["budget"]["tripped"] == rec_doc["budget"]["tripped"]
    assert rep_doc["budget"]["used"]["cost_usd"] == rec_doc["budget"]["used"]["cost_usd"]
    assert rep_doc["iterations"] == rec_doc["iterations"]


def test_unit_cost_suffix():
    spec = ModelSpec(
        id="mock/cheap",
        provider="scripted",
        tier="cheap",
        input_usd_per_mtok=1.0,
        output_usd_per_mtok=2.0,
    )
    rec = CostMeter().record(spec, "cheap", "react", 10, 5, replayed=True)
    assert rec.cost_source.endswith("+replay")

    self_hosted = dataclasses.replace(spec, cost_model="self_hosted")
    meter = CostMeter()
    meter.record(self_hosted, "cheap", "react", 10, 5, replayed=True)
    assert meter.total_cost_usd == 0
