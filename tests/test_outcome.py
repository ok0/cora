from __future__ import annotations

import signal
from pathlib import Path

from cora.core.agent import RunResult
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.outcome import (
    OUTCOME_KEYS,
    error_outcome,
    exit_code,
    outcome_dict,
    outcome_stop_reason,
)
from cora.core.state import Session, StopReason


def _result(stop: StopReason, answer: str | None = "ans", summary: dict | None = None) -> RunResult:
    base = {"total_cost_usd": 0.0, "by_model": {}}
    return RunResult(
        Session(id="s", task="t"),
        answer,
        stop,
        summary if summary is not None else base,
        Path("x"),
    )


def test_exit_codes():
    assert exit_code("final_answer") == 0
    assert exit_code("check_failed") == 1
    assert exit_code("tripwire") == 1
    assert exit_code("budget_exceeded") == 4
    assert exit_code("policy_blocked") == 5
    assert exit_code("interrupted", signal=signal.SIGINT) == 130
    assert exit_code("interrupted", signal=signal.SIGTERM) == 143
    assert exit_code("interrupted") == 130


def test_stop_reason_precedence():
    denied = {"total_cost_usd": 0.0, "by_model": {}, "policy": {"deny": 1, "ask_resolved_deny": 0}}
    assert outcome_stop_reason(_result(StopReason.COST_LIMIT)) == "budget_exceeded"
    assert outcome_stop_reason(_result(StopReason.MAX_ITERATIONS)) == "budget_exceeded"
    assert outcome_stop_reason(_result(StopReason.BUDGET_EXCEEDED)) == "budget_exceeded"
    assert outcome_stop_reason(_result(StopReason.FINAL_ANSWER, summary=denied)) == "final_answer"
    assert outcome_stop_reason(_result(StopReason.CHECK_FAILED, summary=denied)) == "policy_blocked"
    assert outcome_stop_reason(_result(StopReason.CHECK_FAILED)) == "check_failed"
    assert outcome_stop_reason(_result(StopReason.FINAL_ANSWER), signal=15) == "interrupted"
    assert (
        outcome_stop_reason(_result(StopReason.CHECK_FAILED), tripped="tool_calls")
        == "budget_exceeded"
    )
    assert outcome_stop_reason(_result(StopReason.TRIPWIRE), denials=1) == "policy_blocked"


def test_outcome_dict_keys():
    r = _result(StopReason.FINAL_ANSWER)
    out = outcome_dict(r, BudgetGovernor(BudgetLimits()), wall_s=1.23456)
    assert set(out) == set(OUTCOME_KEYS)
    assert out["wall_s"] == 1.235
    assert out["ok"] is True


def test_error_outcome():
    out = error_outcome("boom")
    assert set(out) == set(OUTCOME_KEYS)
    assert out["ok"] is False
    assert out["errors"] == ["boom"]
    assert out["exit_code"] == 2
    assert out["tokens"] == {"in": 0, "out": 0}
