from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from conftest import PY, act, native, run_repl, tc, with_agent, with_gates_off, write_files
from cora.core.agent import Agent
from cora.core.config import ConfigError, load_config, parse_config
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.tripwire import Tripwire, normalize_error

PASS_IF_GOOD = f"{PY} -c \"import sys; sys.exit(0 if open('a.txt').read().strip()=='good' else 1)\""
FAIL = f"{PY} -c \"print('boom'); raise SystemExit(1)\""
EDIT = act("edit_file", {"path": "a.txt", "old": "bad", "new": "good"})


def no_strong(**agent):
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                }
            ],
            "agent": {"approval": "auto", **agent},
        }
    )


def step(protocol, tool, args, i=1):
    if protocol == "react":
        return act(tool, args)
    return native(tc(tool, args, f"c{i}"))


def final(protocol, text):
    return f"Final Answer: {text}" if protocol == "react" else native(text=text)


def events(r, kind=None):
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def test_tripwire_normalize_unit():
    assert normalize_error("x /tmp/a/b.py:12 at 0xdeadbeef in 0.03s") == normalize_error(
        "x /var/q.py:99 at 0x1 in 1.5s"
    )
    assert normalize_error("error A") != normalize_error("error B")
    t = Tripwire()
    assert [t.observe("tool", "n", "A") for _ in range(3)] == [False, False, True]
    t2 = Tripwire()
    assert not any(t2.observe("tool", "n", x) for x in ["A", "B"] * 3)


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_no_check_no_sensor_effects(protocol, mock_config, scripted, ws):
    cfg = with_agent(mock_config, tool_protocol=protocol)
    scripted.script[:] = [step(protocol, "list_files", {}), final(protocol, "ok")]
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run("hi"))
    assert len(scripted.calls) == 2
    assert "sensor" not in r.summary
    assert not {e["type"] for e in events(r)} & {"check", "tripwire", "tool_groups"}

    scripted.script[:] = [step(protocol, "list_files", {}), final(protocol, "ok")]
    scripted.calls.clear()
    r = asyncio.run(
        Agent(cfg, ws, ApprovalPolicy("auto")).run("hi", check_command=None, sensor=True)
    )
    assert len(scripted.calls) == 2
    assert "sensor" not in r.summary
    assert not {e["type"] for e in events(r)} & {"check", "tripwire", "tool_groups"}


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_sensor_fail_then_pass(protocol, mock_config, scripted, ws):
    write_files(ws, {"a.txt": "bad"})
    cfg = with_gates_off(mock_config, tool_protocol=protocol)
    scripted.script[:] = [
        final(protocol, "done"),
        step(protocol, "edit_file", {"path": "a.txt", "old": "bad", "new": "good"}),
        final(protocol, "fixed"),
    ]
    r = asyncio.run(
        Agent(cfg, ws, ApprovalPolicy("auto")).run(
            "fix a.txt", check_command=PASS_IF_GOOD, sensor=True
        )
    )
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "fixed"
    assert len(scripted.calls) == 3
    assert scripted.calls[1].messages[-1].content.startswith(
        "Observation: the check command failed"
    )
    assert [e["ok"] for e in events(r, "check")] == [False, True]
    s = r.summary["sensor"]
    assert s["checks"] == 2
    assert s["retries"] == 1
    assert s["extra_calls"] == 2
    assert s["extra_cost_usd"] > 0


def test_sensor_retry_cap(mock_config, scripted, ws):
    cfg = with_agent(mock_config, sensor_max_retries=1)
    scripted.script[:] = ["Final Answer: a"] * 5
    r = asyncio.run(
        Agent(cfg, ws, ApprovalPolicy("auto")).run("hi", check_command=FAIL, sensor=True)
    )
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert len(scripted.calls) == 2
    assert len(events(r, "check")) == 2
    assert "boom" in r.session.last_failure
    assert r.answer == "a"


def test_sensor_cap_default_distinct_outputs(mock_config, scripted, ws):
    check = (
        f"{PY} -c \"import pathlib;p=pathlib.Path('n.txt');n=len(p.read_text()) if p.exists() "
        "else 0;p.write_text('x'*(n+1));print('fail'+'abcdefgh'[n]);raise SystemExit(1)\""
    )
    scripted.script[:] = ["Final Answer: a"] * 5
    r = asyncio.run(Agent(mock_config, ws, ApprovalPolicy("auto")).run(
        "hi", check_command=check, sensor=True
    ))
    assert len(events(r, "check")) == 4
    assert not events(r, "tripwire")
    assert r.stop_reason == StopReason.CHECK_FAILED


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_tripwire_tool_errors_stop_without_strong(protocol, scripted, ws):
    cfg = no_strong(tripwire=True)
    cfg = with_agent(cfg, tool_protocol=protocol)
    scripted.script[:] = [
        step(protocol, "read_file", {"path": "missing.txt"}, i) for i in range(5)
    ]
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run("hi"))
    assert r.stop_reason == StopReason.TRIPWIRE
    assert len(scripted.calls) == 3
    assert "tripwire" in r.session.last_failure


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_tripwire_alternating_errors_no_trip(protocol, scripted, ws):
    cfg = with_agent(no_strong(tripwire=True), tool_protocol=protocol)
    items = []
    for i in range(3):
        items.append(step(protocol, "read_file", {"path": "missing.txt"}, 2 * i))
        items.append(step(protocol, "search", {"pattern": "("}, 2 * i + 1))
    items.append(final(protocol, "ok"))
    scripted.script[:] = items
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run("hi"))
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert len(scripted.calls) == 7
    assert not events(r, "tripwire")


def test_tripwire_check_failures(mock_config, scripted, ws):
    scripted.script[:] = ["Final Answer: a"] * 5
    r = asyncio.run(
        Agent(no_strong(), ws, ApprovalPolicy("auto")).run("hi", check_command=FAIL, sensor=True)
    )
    assert r.stop_reason == StopReason.TRIPWIRE
    assert len(events(r, "check")) == 3
    assert len(scripted.calls) == 3

    scripted.script[:] = ["Final Answer: a"] * 5
    scripted.calls.clear()
    r = asyncio.run(
        Agent(mock_config, ws, ApprovalPolicy("auto")).run("hi", check_command=FAIL, sensor=True)
    )
    escalations = [e for e in events(r, "tripwire") if e["action"] == "escalate"]
    assert len(escalations) == 1
    assert scripted.calls[3].model == "mock/strong"
    assert len(events(r, "check")) == 4
    assert r.stop_reason == StopReason.CHECK_FAILED


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_tripwire_escalates_once_then_stops(protocol, mock_config, scripted, ws):
    cfg = with_agent(mock_config, tripwire=True, tool_protocol=protocol)
    items = [step(protocol, "read_file", {"path": "missing.txt"}, i) for i in range(6)]
    items.append(final(protocol, "ok"))
    scripted.script[:] = items
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run("hi"))
    assert r.stop_reason == StopReason.TRIPWIRE
    assert len(scripted.calls) == 6
    assert scripted.calls[2].model == "mock/cheap"
    assert scripted.calls[3].model == "mock/strong"
    assert [e["action"] for e in events(r, "tripwire")] == ["escalate", "stop"]
    assert len(events(r, "route")) == 2
    assert "same tool error happened 3 times" in scripted.calls[3].messages[-1].content
    assert r.session.escalated
    assert "after one escalation" in r.session.last_failure


def test_repl_check_command(ws, cfg_file, scripted):
    write_files(ws, {"a.txt": "bad"})
    scripted.script[:] = ["Final Answer: done", EDIT, "Final Answer: fixed"]
    out = run_repl(
        ws,
        cfg_file,
        [
            "/check",
            f"/check {PASS_IF_GOOD}",
            "/check",
            "fix a.txt",
            "/status",
            "/check off",
            "/check",
            "/exit",
        ],
    )
    assert out.count("check: off") >= 2
    assert f"check: {PASS_IF_GOOD}" in out
    assert "sensor: 2 checks" in out
    assert (ws / "a.txt").read_text(encoding="utf-8") == "good"

    out = run_repl(ws, cfg_file, ["/check", "/exit"])
    assert "check: off" in out


@pytest.mark.slow
def test_check_follows_shell_policy(mock_config, scripted, ws):
    cfg = with_agent(mock_config, shell_timeout_s=1, sensor_max_retries=0)
    scripted.script[:] = ["Final Answer: x"]
    r = asyncio.run(
        Agent(cfg, ws, ApprovalPolicy("auto")).run(
            "hi", check_command=f"{PY} -c \"import time; time.sleep(5)\"", sensor=True
        )
    )
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert "timeout after 1s" in r.session.last_failure

    cfg = with_agent(mock_config, sensor_max_retries=1)
    scripted.script[:] = ["Final Answer: x", "Final Answer: y"]
    scripted.calls.clear()
    r = asyncio.run(
        Agent(cfg, ws, ApprovalPolicy("auto")).run(
            "hi", check_command=f"{PY} -c \"print('x'*20000); raise SystemExit(1)\"", sensor=True
        )
    )
    assert "Output (last 2000 chars)" in scripted.calls[1].messages[-1].content
    assert len(r.session.last_failure) <= 2000
    assert all(len(e["output_head"]) <= 500 for e in events(r, "check"))

    scripted.script[:] = [act("run_shell", {"command": "echo hacked"}), "Final Answer: x"]
    scripted.calls.clear()
    agent = Agent(mock_config, ws, ApprovalPolicy("deny"))
    r = asyncio.run(agent.run("hi", check_command="exit 0", sensor=True))
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert any("denied by user" in m.content for m in scripted.calls[1].messages)
    assert [e["command"] for e in events(r, "check")] == ["exit 0"]
    assert r.session.check_command == "exit 0"
    assert not any("check" in n for n in agent.registry_for().names())


def test_sensor_config_validation():
    with pytest.raises(ConfigError, match="sensor_max_retries"):
        no_strong(sensor_max_retries=-1)
    with pytest.raises(ConfigError, match="sensor_feedback_chars"):
        no_strong(sensor_feedback_chars=10)
    with pytest.raises(ConfigError, match="tripwire"):
        no_strong(tripwire="y")
    root = Path(__file__).resolve().parents[1]
    assert load_config(root / "cora.toml").agent.sensor_max_retries == 3
