from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from conftest import native, tc, with_agent, write_files
from cora.core.agent import Agent
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.tripwire import Tripwire

FIXTURE = (
    Path(__file__).parent
    / "fixtures/m20d/artifacts/m20d-deepseek-v2/e2e_n08-r2"
    / "sessions/20261028-120515-8eca84/events.jsonl"
)


def _fixture_rows() -> list[dict]:
    return [json.loads(x) for x in FIXTURE.read_text(encoding="utf-8").splitlines()]


def _cmds() -> list[str]:
    rows = _fixture_rows()
    denials = [rows[i - 1] for i in range(24, 29)]
    failures = [rows[i - 1] for i in range(32, 37)]
    assert all(r["type"] == "policy_decision" and r["rule"] == "confine:cd" for r in denials)
    assert all(r["type"] == "tool_call" and r["tool"] == "run_shell" for r in failures)
    assert all(r["ok"] is False for r in failures)
    return [r["args"] for r in denials]


CMDS = _cmds()


def _ws_with_module(ws: Path) -> None:
    (ws / "contacts").mkdir()
    write_files(
        ws, {"contacts/normalize.py": "def normalize_email(s: str) -> str:\n    return s\n"}
    )


def _run(cfg, ws):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("policy")).run("fix normalize"))


def _same_response_calls(prefix: str) -> list:
    return [tc("run_shell", {"command": c}, f"{prefix}{i}") for i, c in enumerate(CMDS)]


def _cfg(mock_config, per_response: bool):
    cfg = with_agent(
        mock_config,
        tripwire=True,
        tool_protocol="native",
        tripwire_per_response=per_response,
    )
    return replace(cfg, router=replace(cfg.router, escalate_on_retry=False))


def test_unit_same_response_counts_once():
    t = Tripwire(per_response=True)
    assert [t.observe("tool", "run_shell", "denied", turn=1) for _ in range(5)] == [False] * 5
    assert t.streak == 1
    assert t.tripped is None
    assert t.observe("tool", "run_shell", "denied", turn=2) is False
    assert t.tripped is None
    assert t.observe("tool", "run_shell", "denied", turn=3) is True
    assert t.tripped is not None

    base = Tripwire()
    assert [base.observe("tool", "run_shell", "denied", turn=1) for _ in range(3)] == [
        False,
        False,
        True,
    ]


def test_n08_r2_turn_off_stops(mock_config, scripted, ws):
    _ws_with_module(ws)
    cfg = _cfg(mock_config, per_response=False)
    scripted.script[:] = [native(*_same_response_calls("c")), native(text="done")]
    r = _run(cfg, ws)
    assert r.stop_reason == StopReason.TRIPWIRE
    assert len(scripted.calls) == 1


def test_n08_r2_turn_on_continues(mock_config, scripted, ws):
    _ws_with_module(ws)
    cfg = _cfg(mock_config, per_response=True)
    scripted.script[:] = [native(*_same_response_calls("c")), native(text="done")]
    r = _run(cfg, ws)
    assert r.stop_reason != StopReason.TRIPWIRE
    assert len(scripted.calls) == 2
    second_request = "\n".join(m.content for m in scripted.calls[1].messages)
    assert "denied by policy (confine:cd)" in second_request
    assert "Hint:" in second_request


def test_on_still_trips_across_responses(mock_config, scripted, ws):
    _ws_with_module(ws)
    cfg = _cfg(mock_config, per_response=True)
    scripted.script[:] = [
        native(tc("run_shell", {"command": CMDS[0]}, "c1")),
        native(tc("run_shell", {"command": CMDS[0]}, "c2")),
        native(tc("run_shell", {"command": CMDS[0]}, "c3")),
        native(text="done"),
    ]
    r = _run(cfg, ws)
    assert r.stop_reason == StopReason.TRIPWIRE
    assert len(scripted.calls) == 3
