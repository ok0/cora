from __future__ import annotations

import asyncio
import tomllib
from dataclasses import replace

import pytest

from conftest import (
    CFG_TOML,
    COMPLEX_PROMPT,
    FIXED_CFG_TOML,
    PY,
    ScriptedProvider,
    act,
    with_agent,
    write_files,
)
from cora.core.agent import Agent
from cora.core.config import parse_config
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from record_util import entries, record_env, seed_ws
from test_sensor import PASS_IF_GOOD, final, step
from test_sensor_ladder import REFLECTION, counting_check, events, run_agent

EDIT = act("edit_file", {"path": "a.txt", "old": "bad", "new": "good"})
LADDER_SCRIPT = ["Final Answer: a"] * 3 + [REFLECTION, "Final Answer: b"] + ["Final Answer: c"] * 3


def esc_cfg(cfg, *, router=None, **esc):
    return replace(
        cfg,
        escalation=replace(cfg.escalation, enabled=True, **esc),
        router=replace(cfg.router, **(router or {})),
    )


def models(r):
    return [e["model"] for e in events(r, "llm_call")]


def test_ladder_exhausted_escalates_once(mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config, ladder=True, sensor_max_retries=2))
    scripted.script[:] = list(LADDER_SCRIPT)
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=True)
    assert len(scripted.calls) == 8
    assert all(c.model == "mock/cheap" for c in scripted.calls[0:5])
    assert all(c.model == "mock/strong" for c in scripted.calls[5:8])
    assert len(events(r, "check")) == 7
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "ladder_exhausted"
    assert esc[0]["model"] == "mock/strong"
    kinds = [e["type"] for e in events(r)]
    assert kinds.index("escalate") > kinds.index("ladder_exhausted")
    assert r.session.escalation_trigger == "ladder_exhausted"
    assert r.session.escalated
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert r.summary["escalation"]["trigger"] == "ladder_exhausted"


def test_ladder_exhausted_disabled_unchanged(mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=True, sensor_max_retries=2)
    scripted.script[:] = list(LADDER_SCRIPT)
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=True)
    assert len(scripted.calls) == 5
    assert not events(r, "escalate")
    assert r.stop_reason == StopReason.CHECK_FAILED


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_stuck_fires(protocol, mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config, tool_protocol=protocol))
    scripted.script[:] = [step(protocol, "list_files", {}, i) for i in range(1, 5)] + [
        final(protocol, "ok")
    ]
    r = run_agent(cfg, ws)
    assert len(scripted.calls) == 5
    assert scripted.calls[3].model == "mock/cheap"
    assert scripted.calls[4].model == "mock/strong"
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "stuck"


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_stuck_reset_by_new_read(protocol, mock_config, scripted, ws):
    write_files(ws, {"a.txt": "content"})
    cfg = esc_cfg(with_agent(mock_config, tool_protocol=protocol))
    scripted.script[:] = [
        step(protocol, "list_files", {}, 1),
        step(protocol, "list_files", {}, 2),
        step(protocol, "read_file", {"path": "a.txt"}, 3),
        step(protocol, "list_files", {}, 4),
        final(protocol, "ok"),
    ]
    r = run_agent(cfg, ws)
    assert not events(r, "escalate")
    assert all(c.model == "mock/cheap" for c in scripted.calls)


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_stuck_reset_by_write(protocol, mock_config, scripted, ws):
    write_files(ws, {"a.txt": "content"})
    cfg = esc_cfg(with_agent(mock_config, tool_protocol=protocol))
    scripted.script[:] = [
        step(protocol, "list_files", {}, 1),
        step(protocol, "list_files", {}, 2),
        step(protocol, "write_file", {"path": "b.txt", "content": "x"}, 3),
        step(protocol, "list_files", {}, 4),
        final(protocol, "ok"),
    ]
    r = run_agent(cfg, ws)
    assert not events(r, "escalate")
    assert all(c.model == "mock/cheap" for c in scripted.calls)


def test_stuck_zero_never_fires(mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config), on_stuck_iterations=0)
    scripted.script[:] = [act("list_files", {})] * 8 + ["Final Answer: ok"]
    r = run_agent(cfg, ws)
    assert not events(r, "escalate")


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_tripwire_trigger(protocol, mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config, tripwire=True, tool_protocol=protocol))
    scripted.script[:] = [
        step(protocol, "read_file", {"path": "missing.txt"}, i) for i in range(1, 7)
    ] + [final(protocol, "ok")]
    r = run_agent(cfg, ws)
    assert scripted.calls[3].model == "mock/strong"
    assert [e["action"] for e in events(r, "tripwire")] == ["escalate", "stop"]
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "tripwire"
    assert r.stop_reason == StopReason.TRIPWIRE


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_tripwire_trigger_on_tripwire_false(protocol, mock_config, scripted, ws):
    cfg = esc_cfg(
        with_agent(mock_config, tripwire=True, tool_protocol=protocol), on_tripwire=False
    )
    scripted.script[:] = [
        step(protocol, "read_file", {"path": "missing.txt"}, i) for i in range(1, 7)
    ] + [final(protocol, "ok")]
    r = run_agent(cfg, ws)
    assert len(scripted.calls) == 3
    assert all(c.model == "mock/cheap" for c in scripted.calls)
    assert not events(r, "escalate")
    assert [e["action"] for e in events(r, "tripwire")] == ["stop"]


def test_budget_fraction(scripted, ws):
    cfg = parse_config(tomllib.loads(FIXED_CFG_TOML))
    cfg = esc_cfg(
        with_agent(cfg, approval="auto", max_cost_usd=0.02),
        on_budget_fraction=0.5,
        on_stuck_iterations=0,
    )
    scripted.script[:] = [act("list_files", {})] * 20
    r = run_agent(cfg, ws)
    assert len(scripted.calls) == 11
    assert scripted.calls[8].model == "mock/cheap"
    assert scripted.calls[9].model == "mock/strong"
    assert scripted.calls[10].model == "mock/strong"
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "budget_fraction"
    assert r.stop_reason == StopReason.COST_LIMIT
    assert events(r, "budget_trip")
    assert r.summary["total_cost_usd"] == pytest.approx(9 * 0.0012 + 2 * 0.006)


def test_budget_fraction_passing_check_no_escalation(scripted, ws):
    cfg = parse_config(tomllib.loads(FIXED_CFG_TOML))
    cfg = esc_cfg(
        with_agent(cfg, approval="auto", max_cost_usd=0.02),
        on_budget_fraction=0.5,
        on_stuck_iterations=0,
    )
    scripted.script[:] = [act("list_files", {})] * 8 + ["Final Answer: done"]
    r = run_agent(
        cfg,
        ws,
        check_command=f"{PY} -c \"raise SystemExit(0)\"",
        sensor=True,
    )
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert not events(r, "escalate")


def test_budget_fraction_zero_never_fires(scripted, ws):
    cfg = parse_config(tomllib.loads(FIXED_CFG_TOML))
    cfg = esc_cfg(
        with_agent(cfg, approval="auto", max_cost_usd=0.02),
        on_budget_fraction=0,
        on_stuck_iterations=0,
    )
    scripted.script[:] = [act("list_files", {})] * 20
    r = run_agent(cfg, ws)
    assert not events(r, "escalate")
    assert all(c.model == "mock/cheap" for c in scripted.calls)
    assert r.stop_reason == StopReason.COST_LIMIT


def test_two_triggers_first_wins(mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config, tripwire=True), on_stuck_iterations=2)
    scripted.script[:] = [act("read_file", {"path": "missing.txt"})] * 6 + [
        "Final Answer: ok"
    ]
    r = run_agent(cfg, ws)
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "stuck"
    assert scripted.calls[2].model == "mock/strong"
    assert r.session.escalation_trigger == "stuck"
    assert [e["action"] for e in events(r, "tripwire")] == ["stop"]
    assert r.stop_reason == StopReason.TRIPWIRE


def test_attempt_trigger_enabled(mock_config, scripted, ws):
    cfg = esc_cfg(with_agent(mock_config, max_attempts=2))
    scripted.script[:] = ["Final Answer: a", REFLECTION, "Final Answer: b"]
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=False)
    assert scripted.calls[2].model == "mock/strong"
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "attempt"
    assert r.session.escalated is True


def test_attempt_trigger_disabled_legacy(mock_config, scripted, ws):
    cfg = with_agent(mock_config, max_attempts=2)
    scripted.script[:] = ["Final Answer: a", REFLECTION, "Final Answer: b"]
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=False)
    assert scripted.calls[2].model == "mock/strong"
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "attempt"
    assert r.session.escalated is False
    assert "escalation" not in r.summary


def test_strong_model_override(mock_config, scripted, ws):
    extra = CFG_TOML + (
        '\n[[models]]\nid = "mock/strong2"\nprovider = "scripted"\ntier = "strong"\n'
        "input_usd_per_mtok = 5.0\noutput_usd_per_mtok = 10.0\n"
    )
    cfg = parse_config(tomllib.loads(extra))
    cfg = esc_cfg(with_agent(cfg), strong_model="mock/strong2", on_stuck_iterations=4)
    scripted.script[:] = [act("list_files", {})] * 4 + ["Final Answer: ok"]
    r = run_agent(cfg, ws)
    assert scripted.calls[4].model == "mock/strong2"
    assert events(r, "escalate")[0]["model"] == "mock/strong2"


def test_cheap_first_starts_cheap(mock_config, scripted, ws):
    cfg = replace(
        with_agent(mock_config, ladder=True, sensor_max_retries=2),
        router=replace(mock_config.router, mode="cheap_first"),
    )
    scripted.script[:] = list(LADDER_SCRIPT)
    r = run_agent(cfg, ws, COMPLEX_PROMPT, check_command=counting_check(), sensor=True)
    assert all(c.model == "mock/cheap" for c in scripted.calls[0:5])
    assert events(r, "route")[0]["tier"] == "cheap"
    assert not events(r, "escalate")

    scripted.calls.clear()
    scripted.script[:] = list(LADDER_SCRIPT)
    cfg_on = esc_cfg(cfg, router={"mode": "cheap_first"})
    r = run_agent(cfg_on, ws, COMPLEX_PROMPT, check_command=counting_check(), sensor=True)
    assert scripted.calls[0].model == "mock/cheap"
    assert scripted.calls[5].model == "mock/strong"
    esc = events(r, "escalate")
    assert len(esc) == 1
    assert esc[0]["trigger"] == "ladder_exhausted"


def test_cheap_first_disabled_never_leaves_cheap(mock_config, scripted, ws):
    cfg = replace(
        with_agent(mock_config, tripwire=True, max_attempts=2),
        router=replace(mock_config.router, mode="cheap_first"),
    )
    scripted.script[:] = [act("read_file", {"path": "missing.txt"})] * 6 + [
        "Final Answer: ok"
    ]
    r = run_agent(cfg, ws, COMPLEX_PROMPT)
    assert scripted.calls
    assert all(c.model == "mock/cheap" for c in scripted.calls)
    assert r.stop_reason == StopReason.TRIPWIRE


def _blocked_init(self, settings) -> None:
    raise AssertionError("provider constructed in replay")


def test_escalation_replay_offline(scripted, tmp_path, monkeypatch, no_network):
    text = CFG_TOML + (
        '\n[router]\nmode = "cheap_first"\n\n[escalation]\nenabled = true\n\n'
        '[agent]\napproval = "auto"\nladder = true\nsensor_max_retries = 1\n'
    )
    cfg = parse_config(tomllib.loads(text))
    script = [
        "Thought: the file looks fine.\nFinal Answer: done",
        "Thought: the file looks fine.\nFinal Answer: done",
        REFLECTION,
        "Thought: I think it is done.\nFinal Answer: done",
        EDIT,
        "Final Answer: fixed",
    ]
    rec = tmp_path / "rec"
    ws_a = seed_ws(tmp_path / "a")
    write_files(ws_a, {"a.txt": "bad"})
    scripted.script[:] = list(script)
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_run = asyncio.run(
        Agent(cfg, ws_a, ApprovalPolicy("auto")).run(
            "fix a.txt", check_command=PASS_IF_GOOD, sensor=True
        )
    )
    assert rec_run.stop_reason == StopReason.FINAL_ANSWER
    assert entries(rec)

    ws_b = seed_ws(tmp_path / "b")
    write_files(ws_b, {"a.txt": "bad"})
    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    rep_run = asyncio.run(
        Agent(cfg, ws_b, ApprovalPolicy("auto")).run(
            "fix a.txt", check_command=PASS_IF_GOOD, sensor=True
        )
    )
    assert rep_run.stop_reason == StopReason.FINAL_ANSWER

    def esc_pairs(r):
        return [(e["trigger"], e["model"]) for e in events(r, "escalate")]

    assert esc_pairs(rec_run) == [("ladder_exhausted", "mock/strong")]
    assert esc_pairs(rep_run) == esc_pairs(rec_run)
    assert models(rep_run) == models(rec_run)
    assert no_network == []
