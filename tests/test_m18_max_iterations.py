from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from conftest import ScriptedProvider, act
from cora.bench.e2e import E2ETask, load_e2e_tasks
from cora.bench.live import run_live_bench
from cora.bench.report import report_json
from cora.core.config import CoraConfig, parse_config
from cora.core.errors import ProviderAccountError
from cora.core.providers import register_provider
from e2e_util import solve_script

pytestmark = pytest.mark.slow


@register_provider("m18_cent")
class M18CentProvider(ScriptedProvider):
    async def complete(self, req):
        return dataclasses.replace(await super().complete(req), cost_usd=0.01)


@register_provider("m18_acct")
class M18AcctProvider(ScriptedProvider):
    async def complete(self, req):
        ScriptedProvider.calls.append(req)
        raise ProviderAccountError(402, "insufficient credits")


@register_provider("m18_sleepy")
class M18SleepyProvider(ScriptedProvider):
    async def complete(self, req):
        await asyncio.sleep(5)
        return await super().complete(req)


LIST = act("list_files", {"path": "."})


def _todo() -> E2ETask:
    return {t.id: t for t in load_e2e_tasks()}["e2e_todo_cli"]


def _cfg(provider: str, model: str) -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": model,
                    "provider": provider,
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )


def _run(config: CoraConfig, task: E2ETask, state: Path, model: str = "mock/cheap"):
    return asyncio.run(
        run_live_bench(
            config,
            models=[model],
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.30,
            max_iterations=40,
            state_dir=state,
        )
    )


def test_max_iterations_with_passing_workspace_is_solved(
    scripted, mock_config, tmp_path: Path, no_network
) -> None:
    task = dataclasses.replace(_todo(), max_iterations=3)
    scripted.script.extend(solve_script(_todo(), "reference")[:-1] + [LIST] * 5)
    rep = _run(mock_config, task, tmp_path / "s")
    r = rep.results[0]
    assert r.end_reason == "max_iterations"
    assert r.stop_reason == "max_iterations"
    assert r.status == "solved"
    assert r.full_pass is True
    assert r.score == 1.0
    assert "end_reason=max_iterations" in r.detail
    obj = json.loads(report_json(rep, None))
    assert obj["results"][0]["status"] == "solved"
    assert obj["results"][0]["end_reason"] == "max_iterations"


def test_max_iterations_with_failing_workspace_is_failed(
    scripted, mock_config, tmp_path: Path, no_network
) -> None:
    task = dataclasses.replace(_todo(), max_iterations=3)
    scripted.script.extend([LIST] * 5)
    r = _run(mock_config, task, tmp_path / "s").results[0]
    assert r.end_reason == "max_iterations"
    assert r.status == "failed"
    assert r.full_pass is False
    assert r.score < 1


def test_cost_limit_status_unchanged(tmp_path: Path, scripted, no_network) -> None:
    task = dataclasses.replace(_todo(), cost_usd=0.005)
    scripted.script.extend([LIST] * 5)
    r = _run(_cfg("m18_cent", "mock/cent"), task, tmp_path / "s", model="mock/cent").results[0]
    assert r.end_reason == "cost_limit"
    assert r.status == "stopped_budget"
    assert r.budget_reason is not None
    assert r.full_pass is False


def test_provider_account_error_status_unchanged(tmp_path: Path, scripted, no_network) -> None:
    r = _run(_cfg("m18_acct", "mock/acct"), _todo(), tmp_path / "s", model="mock/acct").results[0]
    assert r.end_reason == "aborted"
    assert r.status == "error"


def test_time_limit_status_unchanged(tmp_path: Path, scripted, no_network) -> None:
    task = dataclasses.replace(_todo(), wall_s=0.3)
    r = _run(
        _cfg("m18_sleepy", "mock/sleepy"), task, tmp_path / "s", model="mock/sleepy"
    ).results[0]
    assert r.end_reason == "time_limit"
    assert r.status == "failed"
