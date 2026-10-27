from __future__ import annotations

import pytest

from conftest import CFG_TOML, act
from cora.core.errors import ProviderError
from cora.core.outcome import OUTCOME_KEYS, error_outcome
from cora.core.types import CompletionResponse
from test_headless import base, doc, events, run_cli, write_cfg
from test_project_cli import THREE, pdoc, statuses, write_plan

DEADLINE = (
    "openrouter request failed: RequestDeadlineExceeded: "
    "no complete response within request_deadline_s=90s"
)


def deadline(req):
    raise ProviderError(DEADLINE)


def billed(text, cost=0.01):
    return CompletionResponse(text, 100, 50, "mock/cheap", cost_usd=cost)


def metered(ws, sid):
    return sum(e["cost_usd"] for e in events(ws, sid) if e["type"] == "llm_call")


def test_error_outcome_cost_args():
    d = error_outcome("x")
    assert d["cost_usd"] == 0.0
    assert d["models"] == []
    d = error_outcome("x", 1, cost_usd=0.5, models=["a"])
    assert d["cost_usd"] == 0.5
    assert d["models"] == ["a"]
    assert set(d) == set(OUTCOME_KEYS)
    assert d["tokens"] == {"in": 0, "out": 0}


def test_headless_deadline_after_billed_call(scripted, ws, cfg_file):
    scripted.script.extend([billed(act("list_files", {})), deadline])
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "error"
    assert "RequestDeadlineExceeded" in d["errors"][0]
    assert d["cost_usd"] > 0
    assert d["cost_usd"] == pytest.approx(metered(ws, d["session_id"]))
    assert d["models"] == ["mock/cheap"]
    assert d["iterations"] == 0
    assert d["tokens"] == {"in": 0, "out": 0}


def test_project_deadline_carries_all_milestones(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend([billed("Final Answer: A"), billed(act("list_files", {})), deadline])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "error"
    assert statuses(d) == ["completed", "interrupted", "pending"]
    assert d["milestones"][1]["cost_usd"] > 0
    total = sum(m["cost_usd"] for m in d["milestones"])
    assert d["cost_usd"] == pytest.approx(total) == pytest.approx(0.02)
    assert d["models"] == ["mock/cheap"]


def test_project_deadline_in_first_milestone_models(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend([billed(act("list_files", {})), deadline])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert statuses(d) == ["interrupted", "pending", "pending"]
    assert d["cost_usd"] == pytest.approx(0.01)
    assert d["models"] == ["mock/cheap"]


def test_project_goal_planner_invalid_carries_planner_cost(scripted, ws, cfg_file):
    scripted.script.extend([billed("x", 0.01), billed("y", 0.02)])
    out = ws / "out.toml"
    args = ["project", "run", "--goal", "g", "--headless", "--json", "-o", str(out)]
    result = run_cli([*args, *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 2
    assert d["run_id"] is None
    assert "after one repair attempt" in d["errors"][0]
    assert d["cost_usd"] == pytest.approx(0.03)
    assert d["models"] == ["mock/cheap"]


def test_pre_run_errors_keep_zero(ws, cfg_file, tmp_path):
    result = run_cli(["run", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["cost_usd"] == 0.0
    assert d["models"] == []

    bad_cfg = write_cfg(
        tmp_path, CFG_TOML.replace('provider = "scripted"', 'provider = "account_fail"'), "bad.toml"
    )
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, bad_cfg)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["cost_usd"] == 0.0
    assert d["models"] == []

    result = run_cli(["project", "run", "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 2
    assert d["cost_usd"] == 0.0
    assert d["models"] == []
