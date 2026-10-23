from __future__ import annotations

import asyncio
import json

import pytest
from typer.testing import CliRunner

from conftest import act
from cora.bench.live import parse_arms, run_ab_bench, run_live_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.report import (
    AB_ARMS,
    AVOIDED_NOTE,
    DIFF_HEADING,
    LiveReport,
    ab_section,
    difficulty_rows,
    report_json,
    report_markdown,
    tier_rows,
)
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config
from cora.core.errors import ConfigError
from cora.core.router import HeuristicRouter, RouteDecision
from explore_mock import EXPLORE_TOML, ExploreMock, explore, turn


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


def test_parse_arms():
    assert parse_arms("all") == AB_ARMS
    assert len(parse_arms("all")) == 5
    assert parse_arms("strong-only,deleg-off,deleg-off") == ("deleg-off", "strong-only")
    with pytest.raises(ConfigError, match="not run"):
        parse_arms("deleg-on+strong-only")
    with pytest.raises(ConfigError, match="not run"):
        parse_arms("deleg-on-par-on-strong-only")
    with pytest.raises(ConfigError, match="at least one"):
        parse_arms("")


def test_ab_all_runs_at_most_five_arms(tmp_path):
    ExploreMock.main = ["Final Answer: 42"] * 5
    report = run_ab(ab_config(), tmp_path, arms=AB_ARMS, tasks=[qtask("1")])
    assert len(report.results) == 5
    assert len({r.arm for r in report.results}) == 5
    with pytest.raises(ConfigError):
        run_ab(
            ab_config(),
            tmp_path,
            arms=["deleg-on-par-on", "deleg-on+strong-only"],
            tasks=[qtask("1")],
        )


def test_ab_delegation_arms_table(tmp_path):
    ExploreMock.main = [
        "Final Answer: 42",
        explore("s1"),
        "Final Answer: 42",
        turn("s2", "s3"),
        "Final Answer: 42",
    ]
    ExploreMock.subs = {name: ["Final Answer: ok"] for name in ("s1", "s2", "s3")}
    ExploreMock.delays = {"s2": 0.05, "s3": 0.05}
    report = run_ab(
        ab_config(),
        tmp_path,
        arms=["deleg-off", "deleg-on-par-off", "deleg-on-par-on"],
        tasks=[qtask("1", minutes=5)],
    )
    by_arm = {r.arm: r for r in report.results}
    assert by_arm["deleg-off"].calls == 1
    assert by_arm["deleg-off"].cost_usd == pytest.approx(0.0012)
    assert by_arm["deleg-on-par-off"].cost_usd == pytest.approx(0.0036)
    assert by_arm["deleg-on-par-off"].deleg_invocations == 1
    assert by_arm["deleg-on-par-on"].cost_usd == pytest.approx(0.0048)
    assert by_arm["deleg-on-par-on"].deleg_max_fanout == 2
    assert by_arm["deleg-on-par-on"].deleg_explore == 2

    rows = {row["arm"]: row for row in json.loads(report_json(report, None))["ab"]["rows"]}
    assert rows["deleg-off"]["resolved_per_dollar"] == pytest.approx(1 / 0.0012)
    assert rows["deleg-on-par-on"]["deleg_max_fanout"] == 2

    md = report_markdown(report, None)
    assert (
        "arms: deleg-off, deleg-on-par-off, deleg-on-par-on | model: mock/cheap | "
        "strong model: n/a | protocol: react"
    ) in md.splitlines()
    assert AVOIDED_NOTE in md
    assert "total_spend_usd:" in md
    assert "budget:" in md
    assert "tools:" in md
    assert "| task | arm | model | status | calls | cost_usd | latency_s |" in md

    data = json.loads(report_json(report, None))
    assert "rows" in data["ab"]
    assert "difficulty_bins" in data


def test_cli_ab_mock(tmp_path):
    cfg_path = tmp_path / "cora.toml"
    cfg_path.write_text(EXPLORE_TOML, encoding="utf-8")
    ExploreMock.main = ["40", explore("s1"), "40", explore("s1"), "40"]
    ExploreMock.subs = {"s1": ["Final Answer: ok", "Final Answer: ok"]}
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "bench",
            "--live",
            "--ab",
            "deleg-off,deleg-on-par-off,deleg-on-par-on",
            "-c",
            str(cfg_path),
            "-w",
            str(tmp_path),
            "--models",
            "mock/cheap",
            "--tasks",
            "query_client_timeout",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output + result.stderr
    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["ab"]["arms"] == ["deleg-off", "deleg-on-par-off", "deleg-on-par-on"]

    bad = runner.invoke(app, ["bench", "--live", "--ab", "x+y", "-c", str(cfg_path)])
    assert bad.exit_code == 2

    two = runner.invoke(
        app,
        [
            "bench",
            "--live",
            "--ab",
            "all",
            "-c",
            str(cfg_path),
            "-w",
            str(tmp_path),
            "--models",
            "mock/cheap,mock/strong",
        ],
    )
    assert two.exit_code == 2
    assert "exactly one" in two.stderr

    no_live = runner.invoke(app, ["bench", "--ab", "all", "-c", str(cfg_path)])
    assert no_live.exit_code == 2
    assert "require --live" in no_live.stderr


def test_ab_strong_only_and_auto_routed(tmp_path, monkeypatch):
    seen: list[tuple[str | None, str]] = []

    class Rec(HeuristicRouter):
        def route(self, prompt, force_tier=None):
            decision = super().route(prompt, force_tier)
            seen.append((self.config.router.pin, decision.tier))
            return decision

    monkeypatch.setattr("cora.core.agent.HeuristicRouter", Rec)
    ExploreMock.main = ["Final Answer: 42"] * 6
    cells: list[tuple] = []
    prev_calls = 0
    prev_seen = 0

    def progress(result, spent):
        nonlocal prev_calls, prev_seen
        cells.append(
            (
                result,
                ExploreMock.calls[prev_calls:],
                seen[prev_seen:],
            )
        )
        prev_calls = len(ExploreMock.calls)
        prev_seen = len(seen)

    report = asyncio.run(
        run_ab_bench(
            ab_config(),
            arms=["deleg-off", "strong-only", "auto-routed"],
            model="mock/cheap",
            protocol="react",
            tasks=[qtask("1", "q1"), qtask("2", "q2")],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=8,
            state_dir=tmp_path / "state",
            on_progress=progress,
        )
    )
    assert len(cells) == 6
    by_arm: dict[str, list] = {}
    for result, reqs, routed in cells:
        by_arm.setdefault(result.arm, []).append((result, reqs, routed))
    for _, reqs, routed in by_arm["strong-only"]:
        assert reqs and all(r.model == "mock/strong" for r in reqs)
        assert all(pin == "mock/strong" for pin, _ in routed)
    for _, reqs, _ in by_arm["deleg-off"]:
        assert reqs and all(r.model == "mock/cheap" for r in reqs)
    for result, _, routed in by_arm["auto-routed"]:
        assert all(pin is None for pin, _ in routed)
        assert result.routes
        assert result.routes[0]["model"] == "mock/cheap"
        assert all("pinned:" not in rt["reason"] for rt in result.routes)

    tiers = tier_rows(report)
    assert tiers is not None
    cheap_status = {r.task: r.status for r in report.results if r.arm == "deleg-off"}
    for row in tiers:
        assert row["cheap_only"] == cheap_status[row["task"]]


class FixedRouter(HeuristicRouter):
    def route(self, prompt, force_tier=None):
        if self.config.router.pin:
            return super().route(prompt, force_tier)
        tier = {"q1": "cheap", "q2": "strong"}[prompt]
        return RouteDecision(self.resolve(tier), tier, 0, ("fixed",), "medium")


def test_ab_auto_routed_tiers_and_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("cora.core.agent.HeuristicRouter", FixedRouter)
    ExploreMock.main = [
        "Final Answer: 0",
        "Final Answer: 42",
        "Final Answer: 0",
        "Final Answer: 0",
        "Final Answer: 42",
        "Final Answer: 42",
    ]
    report = run_ab(
        ab_config(),
        tmp_path,
        arms=["deleg-off", "strong-only", "auto-routed"],
        tasks=[qtask("1", "q1"), qtask("2", "q2")],
    )
    data = json.loads(report_json(report, None))
    rows = {row["task"]: row for row in data["ab"]["per_task_tiers"]}
    assert rows["t1"]["auto_tiers"] == ["cheap"]
    assert rows["t1"]["flags"] == ["routed_cheap_cheap_failed", "only_strong_solved"]
    assert rows["t2"]["auto_tiers"] == ["strong"]
    assert rows["t2"]["flags"] == ["only_strong_solved"]
    md = report_markdown(report, None)
    assert (
        "| t1 | n/a | failed | solved | failed | cheap | "
        "routed_cheap_cheap_failed, only_strong_solved |"
    ) in md


def test_ab_multiple_route_decisions(tmp_path):
    ExploreMock.main = [act("read_file", {"path": "missing.txt"})] * 3 + ["Final Answer: 42"]
    report = run_ab(
        ab_config(),
        tmp_path,
        arms=["auto-routed"],
        tasks=[qtask("3", "q3")],
        sensor=True,
    )
    result = report.results[0]
    assert [rt["tier"] for rt in result.routes] == ["cheap", "strong"]
    assert result.routes[1]["grade"] == "escalated"
    md = report_markdown(report, None)
    assert "cheap>strong" in md


def test_ab_difficulty_aggregation(tmp_path, scripted):
    cfg = ab_config(provider="fixed_usage")
    tasks = [
        qtask("a", "qa", minutes=1.0),
        qtask("b", "qb", minutes=5),
        qtask("c", "qc", minutes=15),
        qtask("d", "qd", minutes=8),
    ]
    scripted.script.extend(
        [
            "Final Answer: 42",
            "Final Answer: 42",
            "Final Answer: 0",
            "Final Answer: 42",
            act("list_files", {}),
            "Final Answer: 42",
            "Final Answer: 42",
            "Final Answer: 42",
            "Final Answer: 42",
        ]
    )
    report = run_ab(cfg, tmp_path, arms=["deleg-off", "strong-only"], tasks=tasks)
    rows = {(r["config"], r["bin"]): r for r in difficulty_rows(report)}
    assert rows[("deleg-off", "easy")]["tasks"] == 1
    assert rows[("deleg-off", "easy")]["solved"] == 1
    assert rows[("deleg-off", "easy")]["cost_usd"] == pytest.approx(0.0012)
    assert rows[("deleg-off", "medium")]["tasks"] == 2
    assert rows[("deleg-off", "medium")]["solved"] == 1
    assert rows[("deleg-off", "medium")]["cost_usd"] == pytest.approx(0.0024)
    assert rows[("deleg-off", "hard")]["tasks"] == 1
    assert rows[("deleg-off", "hard")]["solved"] == 1
    assert rows[("deleg-off", "hard")]["cost_usd"] == pytest.approx(0.0024)
    assert rows[("strong-only", "easy")]["cost_usd"] == pytest.approx(0.006)
    assert rows[("strong-only", "medium")]["tasks"] == 2
    assert rows[("strong-only", "medium")]["solved"] == 2
    assert rows[("strong-only", "medium")]["cost_usd"] == pytest.approx(0.012)
    assert rows[("strong-only", "hard")]["cost_usd"] == pytest.approx(0.006)
    for arm, bin_name in rows:
        expected = sum(
            r.latency_s
            for r in report.results
            if r.arm == arm and (r.difficulty or "unlabeled") == bin_name
        )
        assert rows[(arm, bin_name)]["wall_s"] == pytest.approx(expected)
    md = report_markdown(report, None)
    assert "| deleg-off | medium | 2 | 1 | 0.002400 | " in md


def test_plain_report_unchanged_and_difficulty_only_when_labeled(tmp_path, scripted):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "fixed_usage",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )
    scripted.script.extend(["Final Answer: 42", "Final Answer: 42"])
    plain = asyncio.run(
        run_live_bench(
            cfg,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[qtask("1"), qtask("2")],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=4,
            state_dir=tmp_path / "state",
        )
    )
    md = report_markdown(plain, None)
    assert "By difficulty" not in md
    assert "A/B" not in md
    assert json.loads(report_json(plain, None))["ab"] is None
    assert ab_section(plain) is None

    scripted.script.extend(["Final Answer: 42"])
    labeled = asyncio.run(
        run_live_bench(
            cfg,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[qtask("1", minutes=5)],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=4,
            state_dir=tmp_path / "state2",
        )
    )
    md = report_markdown(labeled, None)
    assert DIFF_HEADING in md
    assert "| mock/cheap react | medium | 1 | 1 |" in md
