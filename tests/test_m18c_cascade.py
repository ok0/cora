from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, ScriptedProvider
from cora.bench.live import run_ab_bench, run_live_bench
from cora.cli.main import app
from cora.core.config import CoraConfig, parse_config
from cora.core.errors import ConfigError
from test_m18c_verify import cfg_cost, make_responder, responder_events, visible_task


def cc_config(with_strong: bool = True) -> CoraConfig:
    models = [
        {
            "id": "mock/other-cheap",
            "provider": "fixed_usage",
            "tier": "cheap",
            "input_usd_per_mtok": 3.0,
            "output_usd_per_mtok": 4.0,
            "supports_tools": True,
        },
        {
            "id": "mock/cheap",
            "provider": "fixed_usage",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 2.0,
            "supports_tools": True,
        },
    ]
    if with_strong:
        models.append(
            {
                "id": "mock/strong",
                "provider": "fixed_usage",
                "tier": "strong",
                "input_usd_per_mtok": 5.0,
                "output_usd_per_mtok": 10.0,
                "supports_tools": True,
            }
        )
    cfg = parse_config({"models": models, "agent": {"approval": "auto"}})
    return replace(
        cfg,
        router=replace(cfg.router, mode="cheap_first"),
        escalation=replace(
            cfg.escalation,
            enabled=True,
            strong_model="mock/other-cheap",
            on_budget_fraction=0.5,
            on_stuck_iterations=4,
            on_tripwire=True,
        ),
        agent=replace(cfg.agent, ladder=True),
    )


def _run_cascade(tmp_path: Path, cfg: CoraConfig, tid: str):
    task = visible_task(
        tmp_path / "e2e", tid, **{"limits.max_iterations": 30, "limits.cost_usd": 0.10}
    )
    return asyncio.run(
        run_ab_bench(
            cfg,
            arms=["auto-routed"],
            model="mock/cheap",
            protocol="react",
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=30,
            state_dir=tmp_path / "state",
            sensor=True,
            sensor_source="auto",
        )
    )


@pytest.mark.slow
def test_cheap_to_cheap_after_ladder_exhausted(tmp_path, scripted):
    scripted.script[:] = [make_responder(["wrong"])] * 60
    report = _run_cascade(tmp_path, cc_config(), "e2e_cc")
    res = report.results[0]
    events = responder_events(tmp_path)

    exhausted = [i for i, e in enumerate(events) if e["type"] == "ladder_exhausted"]
    escalates = [i for i, e in enumerate(events) if e["type"] == "escalate"]
    assert len(exhausted) == 1
    assert len(escalates) == 1
    esc = events[escalates[0]]
    assert esc["trigger"] == "ladder_exhausted"
    assert esc["model"] == "mock/other-cheap"
    assert esc["tier"] == "cheap"
    assert esc["from_model"] == "mock/cheap"
    assert escalates[0] > exhausted[0]
    llm = [i for i, e in enumerate(events) if e["type"] == "llm_call"]
    before = [events[i] for i in llm if i < escalates[0]]
    after = [events[i] for i in llm if i > escalates[0]]
    assert before and all(e["model"] == "mock/cheap" for e in before)
    assert after and after[0]["model"] == "mock/other-cheap"

    assert {r["model"] for r in res.routes} == {"mock/cheap", "mock/other-cheap"}
    calls = ScriptedProvider.calls
    n1 = sum(c.model == "mock/cheap" for c in calls)
    n2 = sum(c.model == "mock/other-cheap" for c in calls)
    assert n2 >= 1
    assert res.cost_usd == pytest.approx(
        n1 * (1000e-6 * 1.0 + 100e-6 * 2.0) + n2 * (1000e-6 * 3.0 + 100e-6 * 4.0)
    )


def test_unknown_strong_model_exits_2(tmp_path, scripted):
    path = tmp_path / "cora.toml"
    path.write_text(
        CFG_TOML + '\n[escalation]\nenabled = true\nstrong_model = "nope/x"\n',
        encoding="utf-8",
    )
    r = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "--suite",
            "e2e",
            "--ab",
            "auto-routed",
            "--models",
            "mock/cheap",
            "--config",
            str(path),
        ],
    )
    assert r.exit_code == 2
    assert "strong_model" in r.output
    assert ScriptedProvider.calls == []


def _run_cc_ab(tmp_path: Path, cfg: CoraConfig, tid: str):
    task = visible_task(
        tmp_path / "e2e", tid, **{"limits.max_iterations": 30, "limits.cost_usd": 0.10}
    )
    return asyncio.run(
        run_ab_bench(
            cfg,
            arms=["auto-routed"],
            model="mock/cheap",
            protocol="react",
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=30,
            state_dir=tmp_path / "state",
            sensor=True,
            sensor_source="auto",
        )
    )


@pytest.mark.slow
def test_cheap_to_cheap_without_strong_tier(tmp_path, scripted):
    scripted.script[:] = [make_responder(["wrong"])] * 60
    report = _run_cc_ab(tmp_path, cc_config(with_strong=False), "e2e_cc_ns")
    assert report.settings["ab"]["escalation_target"] == "mock/other-cheap"
    assert report.settings["ab"]["strong_model"] is None
    assert [m["id"] for m in report.settings["models"]] == ["mock/cheap", "mock/other-cheap"]
    escalates = [e for e in responder_events(tmp_path) if e["type"] == "escalate"]
    assert len(escalates) == 1
    assert escalates[0]["model"] == "mock/other-cheap"


@pytest.mark.slow
def test_auto_routed_target_recorded_with_strong_tier(tmp_path, scripted):
    scripted.script[:] = [make_responder(["wrong"])] * 60
    report = _run_cc_ab(tmp_path, cc_config(), "e2e_cc_st")
    assert report.settings["ab"]["escalation_target"] == "mock/other-cheap"
    assert report.settings["ab"]["strong_model"] == "mock/strong"
    ids = [m["id"] for m in report.settings["models"]]
    assert "mock/other-cheap" in ids
    assert "mock/strong" not in ids


def test_auto_routed_without_target_rejected(tmp_path, scripted):
    cfg = cc_config(with_strong=False)
    cfg = replace(cfg, escalation=replace(cfg.escalation, strong_model=None))
    with pytest.raises(ConfigError, match="priced escalation target"):
        _run_cc_ab(tmp_path, cfg, "e2e_cc_nt")
    assert ScriptedProvider.calls == []


def test_verify_attempts_rejects_ladder(tmp_path, scripted):
    cfg = replace(cfg_cost(), agent=replace(cfg_cost().agent, ladder=True))
    task = visible_task(tmp_path / "e2e", "e2e_ladder")
    with pytest.raises(ConfigError, match="ladder"):
        asyncio.run(
            run_live_bench(
                cfg,
                models=["mock/cheap"],
                protocols=["react"],
                tasks=[task],
                max_cost_usd=0.30,
                max_task_cost_usd=0.10,
                max_iterations=12,
                state_dir=tmp_path / "state",
                verify_attempts=3,
            )
        )
    with pytest.raises(ConfigError, match="ladder"):
        asyncio.run(
            run_ab_bench(
                cfg,
                arms=["deleg-off"],
                model="mock/cheap",
                protocol="react",
                tasks=[task],
                max_cost_usd=0.30,
                max_task_cost_usd=0.10,
                max_iterations=12,
                state_dir=tmp_path / "state",
                verify_attempts=3,
            )
        )
    assert ScriptedProvider.calls == []


def test_verify_attempts_ladder_cli_exit_2(tmp_path, scripted):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + "\n[agent]\nladder = true\n", encoding="utf-8")
    r = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "--suite",
            "e2e",
            "--verify-attempts",
            "3",
            "--models",
            "mock/cheap",
            "--config",
            str(path),
        ],
    )
    assert r.exit_code == 2
    assert "ladder" in r.output
    assert "Traceback" not in r.output
    assert ScriptedProvider.calls == []
