from __future__ import annotations

import asyncio
import json

import pytest

from conftest import PY, with_agent
from cora.core.agent import Agent
from cora.core.reflexion import limit_sentences
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy

REFLECTION = "One. Two. Three. Four. Five. Six. Seven."


def counting_check(pass_at=None):
    cond = "False" if pass_at is None else f"n + 1 == {pass_at}"
    code = (
        "import pathlib,sys;p=pathlib.Path('n.txt');"
        "n=len(p.read_text()) if p.exists() else 0;"
        "p.write_text('x'*(n+1));"
        f"print('fail'+'abcdefgh'[n]);sys.exit(0 if {cond} else 1)"
    )
    return f"{PY} -c \"{code}\""


def events(r, kind=None):
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run_agent(cfg, ws, task="hi", **kwargs):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task, **kwargs))


@pytest.mark.parametrize("sensor", [True, False])
def test_ladder_exhausted(sensor, mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=True, sensor_max_retries=2)
    scripted.script[:] = ["Final Answer: a"] * 3 + [REFLECTION, "Final Answer: b"]
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=sensor)
    assert len(scripted.calls) == 5
    checks = events(r, "check")
    assert len(checks) == 4
    assert all(e["sensor"] is True for e in checks)
    assert r.summary["sensor"]["retries"] == 2
    assert len(events(r, "ladder_reflect")) == 1
    reflections = events(r, "reflection")
    assert len(reflections) == 1
    assert reflections[0]["text"] == "One. Two. Three. Four. Five."
    content = scripted.calls[4].messages[0].content
    assert "Lessons from previous failed attempts" in content
    assert "Five." in content
    assert "Six." not in content
    exhausted = events(r, "ladder_exhausted")
    assert len(exhausted) == 1
    kinds = [e["type"] for e in events(r)]
    assert kinds.index("ladder_exhausted") > [
        i for i, k in enumerate(kinds) if k == "check"
    ][3]
    assert r.session.ladder_exhausted is True
    assert r.summary["sensor"]["ladder_exhausted"] is True
    assert r.stop_reason == StopReason.CHECK_FAILED
    routes = events(r, "route")
    assert routes[-1]["tier"] == routes[0]["tier"]


def test_ladder_passes_on_retry(mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=True, sensor_max_retries=2)
    scripted.script[:] = ["Final Answer: a"] * 2
    r = run_agent(cfg, ws, check_command=counting_check(pass_at=2), sensor=True)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert not events(r, "reflection")
    assert not events(r, "ladder_exhausted")
    assert r.summary["sensor"]["ladder_exhausted"] is False


def test_ladder_passes_after_reflection(mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=True, sensor_max_retries=2)
    scripted.script[:] = ["Final Answer: a"] * 3 + [REFLECTION, "Final Answer: b"]
    r = run_agent(cfg, ws, check_command=counting_check(pass_at=4), sensor=True)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "b"
    assert len(events(r, "reflection")) == 1
    assert not events(r, "ladder_exhausted")


def test_ladder_off_unchanged(mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=False, sensor_max_retries=1)
    scripted.script[:] = ["Final Answer: a"] * 5
    r = run_agent(cfg, ws, check_command=counting_check(), sensor=True)
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert len(scripted.calls) == 2
    assert not events(r, "reflection")
    assert not events(r, "ladder_reflect")
    assert not events(r, "ladder_exhausted")
    assert "ladder_exhausted" not in r.summary["sensor"]


def test_ladder_no_gate(mock_config, scripted, ws):
    cfg = with_agent(mock_config, ladder=True)
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws)
    assert not [e for e in events(r) if e["type"].startswith("ladder_")]
    assert "sensor" not in r.summary


def test_limit_sentences():
    assert limit_sentences(REFLECTION, 5) == "One. Two. Three. Four. Five."
    assert limit_sentences("short", 5) == "short"
