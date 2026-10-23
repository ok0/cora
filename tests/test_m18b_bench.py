from __future__ import annotations

import asyncio
import json

import pytest

from conftest import act
from cora.bench.e2e import E2ETask, load_e2e_tasks
from cora.bench.live import run_ab_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.report import LiveReport, report_json, report_markdown
from cora.core.config import CoraConfig, parse_config
from e2e_util import GRADER_OK, make_task
from explore_mock import ExploreMock, explore


@pytest.fixture(autouse=True)
def _reset_mock():
    ExploreMock.reset()
    ExploreMock.usage = (1000, 100)


def ab_config(provider: str = "explore_mock") -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/other-cheap",
                    "provider": provider,
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/cheap",
                    "provider": provider,
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": provider,
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def run_ab(cfg: CoraConfig, tmp_path, *, arms, tasks, **kwargs) -> LiveReport:
    base = dict(
        model="mock/cheap",
        protocol="react",
        max_cost_usd=0.30,
        max_task_cost_usd=0.10,
        max_iterations=8,
        state_dir=tmp_path / "state",
    )
    base.update(kwargs)
    return asyncio.run(run_ab_bench(cfg, arms=arms, tasks=tasks, **base))


def qtask(i: str, prompt: str = "q", minutes: float | None = None) -> LiveTask:
    return LiveTask(
        f"t{i}",
        "query",
        prompt,
        {"f.txt": "x"},
        answer_regex=r"\b42\b",
        estimated_minutes=minutes,
    )


def _md_cell(md: str, arm: str, col: str) -> str:
    header = next(line for line in md.splitlines() if line.startswith("| arm | model |"))
    row = next(line for line in md.splitlines() if line.startswith(f"| {arm} |"))
    head_cells = [c.strip() for c in header.split("|")]
    row_cells = [c.strip() for c in row.split("|")]
    return row_cells[head_cells.index(col)]


def test_report_attempt_fields(tmp_path):
    ExploreMock.subs = {"s1": ["Final Answer: ok"]}
    ExploreMock.main = [
        explore("s1"),
        "Final Answer: 42",
        act("delegate", {"task": "x", "mode": "bogus"}),
        "Final Answer: 42",
        "Thought: x\nAction: delegate\n",
        "Final Answer: 42",
    ]
    report = run_ab(
        ab_config(),
        tmp_path,
        arms=["deleg-on-par-on"],
        tasks=[qtask("1"), qtask("2"), qtask("3")],
    )
    assert sorted(
        (r.deleg_attempts, r.deleg_invocations, r.deleg_attempts_unparsed) for r in report.results
    ) == [(1, 0, 0), (1, 0, 1), (1, 1, 0)]

    rows = json.loads(report_json(report, None))["ab"]["rows"]
    assert rows[0]["deleg_attempts"] == 3
    assert rows[0]["deleg_attempts_unparsed"] == 1

    md = report_markdown(report, None)
    assert "| deleg_calls | deleg_attempts | deleg_explore |" in md
    assert _md_cell(md, "deleg-on-par-on", "deleg_attempts") == "3"
    assert _md_cell(md, "deleg-on-par-on", "deleg_calls") == "1"


def _synthetic_e2e(root) -> E2ETask:
    task_dir = make_task(root, "e2e_deleg_ws", GRADER_OK)
    pkg = task_dir / "template" / "pkg"
    pkg.mkdir()
    for i in range(30):
        (pkg / f"mod_{i:02d}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    task = load_e2e_tasks(root)[0]
    assert sum(1 for p in (task_dir / "template").rglob("*") if p.is_file()) >= 30
    return task


def test_e2e_deleg_on_par_on_strict_policy(tmp_path):
    task = _synthetic_e2e(tmp_path / "e2e")

    ExploreMock.subs = {"find helpers": [act("list_files", {}), "Final Answer: found"]}
    ExploreMock.main = [explore("find helpers"), "Final Answer: done"]
    report = run_ab(ab_config(), tmp_path, arms=["deleg-on-par-on"], tasks=[task])
    res = report.results[0]
    assert res.deleg_attempts == 1
    assert res.deleg_invocations == 1
    assert res.policy_denies == 0
    sub_reqs = [
        r
        for r in ExploreMock.calls
        if len(r.messages) > 1 and r.messages[1].content.startswith("Task: ")
    ]
    assert sub_reqs
    assert all(r.model == "mock/cheap" for r in sub_reqs)

    ExploreMock.reset()
    ExploreMock.usage = (1000, 100)
    ExploreMock.main = [act("delegate", {"task": "x", "mode": "bogus"}), "Final Answer: done"]
    report2 = run_ab(
        ab_config(),
        tmp_path,
        arms=["deleg-on-par-on"],
        tasks=[task],
        state_dir=tmp_path / "s2",
    )
    res2 = report2.results[0]
    assert res2.deleg_attempts == 1
    assert res2.deleg_invocations == 0
