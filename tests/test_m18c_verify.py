from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

from conftest import ScriptedProvider, act
from cora.bench import e2e
from cora.bench.e2e import E2ETask, load_e2e_tasks
from cora.bench.live import (
    DEFAULT_BENCH_TOOL_GROUPS,
    _arm_config,
    _run_config,
    run_live_bench,
    validate_verify_attempts,
)
from cora.bench.live_tasks import LiveTask
from cora.core.checks import PYTEST_COMMAND, detect_check_command
from cora.core.config import AgentSettings, CoraConfig, ToolGroupSettings, apply_pin, parse_config
from cora.core.errors import ConfigError
from cora.core.observability import read_events
from cora.core.providers import register_provider
from cora.core.toolgroups import OPTIONAL_GROUPS
from e2e_util import make_task

REFLECT_PREFIX = "You attempted a task and failed."
VISIBLE_TEST = (
    "from pathlib import Path\n"
    "def test_answer():\n"
    '    assert not Path(".cora_grader").exists()\n'
    '    p = Path("n.txt"); n = len(p.read_text()) if p.exists() else 0\n'
    '    p.write_text("x" * (n + 1))\n'
    '    ok = Path("answer.txt").is_file() and Path("answer.txt").read_text().strip() == "right"\n'
    '    assert ok, "fail" + "abcdefghijklmnop"[n]\n'
)
GRADER_ANSWER = (
    "import json, pathlib; p = pathlib.Path('answer.txt'); "
    "ok = p.is_file() and p.read_text().strip() == 'right'; "
    "print(json.dumps({'checks': [{'name': 'answer', 'passed': ok}]}))"
)


def visible_task(root: Path, tid: str, **limits) -> E2ETask:
    make_task(
        root,
        tid,
        GRADER_ANSWER,
        **{"limits.max_iterations": 12, "limits.cost_usd": 0.10, **limits},
    )
    test_path = root / tid / "template" / "tests" / "test_visible.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(VISIBLE_TEST, encoding="utf-8")
    task = load_e2e_tasks(root)[0]
    assert task.grader_visibility == "hidden"
    assert detect_check_command(task.template_dir) == PYTEST_COMMAND
    return task


def make_responder(answers: list[str]):
    refl = 0

    def respond(req) -> str:
        nonlocal refl
        if req.messages[-1].content.startswith(REFLECT_PREFIX):
            refl += 1
            return "LESSON-M18C: write the right answer."
        if not any(m.role == "assistant" for m in req.messages):
            content = answers[min(refl, len(answers) - 1)]
            return act("write_file", {"path": "answer.txt", "content": content})
        return "Final Answer: done"

    return respond


@register_provider("m18c_cost")
class M18cCostProvider(ScriptedProvider):
    per_call: ClassVar[float] = 0.001
    after_reflection: ClassVar[float | None] = None
    refl_seen: ClassVar[int] = 0

    async def complete(self, req):
        is_refl = req.messages[-1].content.startswith(REFLECT_PREFIX)
        cls = M18cCostProvider
        if cls.after_reflection is None or cls.refl_seen == 0:
            cost = cls.per_call
        else:
            cost = cls.after_reflection
        resp = await super().complete(req)
        if is_refl:
            cls.refl_seen += 1
        return dataclasses.replace(resp, cost_usd=cost)


@pytest.fixture(autouse=True)
def _reset_cost_provider():
    M18cCostProvider.per_call = 0.001
    M18cCostProvider.after_reflection = None
    M18cCostProvider.refl_seen = 0
    yield
    M18cCostProvider.per_call = 0.001
    M18cCostProvider.after_reflection = None
    M18cCostProvider.refl_seen = 0


def cfg_cost() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "m18c_cost",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": "m18c_cost",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def run_e2e(cfg: CoraConfig, tmp_path: Path, task: E2ETask, **kw):
    return asyncio.run(
        run_live_bench(
            cfg,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=12,
            state_dir=tmp_path / "state",
            **kw,
        )
    )


def responder_events(tmp_path: Path, kind: str | None = None) -> list[dict]:
    rows = [e for p in sorted((tmp_path / "state").rglob("events.jsonl")) for e in read_events(p)]
    return [e for e in rows if kind is None or e["type"] == kind]


@pytest.mark.slow
def test_verify_three_attempts_solved(tmp_path, scripted, monkeypatch):
    task = visible_task(tmp_path / "e2e", "e2e_v3")
    order: list[str] = []
    workspaces: list[Path] = []
    real_prepare = e2e.prepare_workspace
    real_grade = e2e.run_grader

    def prepare(t, tmp):
        ws = real_prepare(t, tmp)
        workspaces.append(ws)
        return ws

    def grade(t, ws, scratch):
        order.append("grade")
        return real_grade(t, ws, scratch)

    monkeypatch.setattr(e2e, "prepare_workspace", prepare)
    monkeypatch.setattr(e2e, "run_grader", grade)
    responder = make_responder(["wrong", "wrong", "right"])

    def guarded(req) -> str:
        order.append("call")
        assert not (workspaces[-1] / ".cora_grader").exists()
        return responder(req)

    scripted.script[:] = [guarded] * 60
    report = run_e2e(cfg_cost(), tmp_path, task, verify_attempts=3)
    res = report.results[0]
    calls = ScriptedProvider.calls

    assert res.status == "solved"
    assert len(responder_events(tmp_path, "reflection")) == 2
    assert len(responder_events(tmp_path, "route")) == 3
    assert order[-1] == "grade"
    assert order.count("grade") == 1
    assert res.cost_usd == pytest.approx(0.001 * len(calls))
    assert res.calls == len(calls)
    first = next(
        i for i, r in enumerate(calls) if r.messages[-1].content.startswith(REFLECT_PREFIX)
    )
    attempt_reqs = [
        r for r in calls[first + 1 :] if not r.messages[-1].content.startswith(REFLECT_PREFIX)
    ]
    assert attempt_reqs
    for req in attempt_reqs:
        assert any("LESSON-M18C" in m.content for m in req.messages)
    assert {c.model for c in calls} == {"mock/cheap"}
    assert not any('name": "answer"' in m.content for req in calls for m in req.messages)
    assert report.settings["verify_attempts"] == 3


@pytest.mark.slow
def test_verify_never_passes_stops_check_failed(tmp_path, scripted):
    task = visible_task(tmp_path / "e2e", "e2e_vnever")
    scripted.script[:] = [make_responder(["wrong"])] * 60
    report = run_e2e(cfg_cost(), tmp_path, task, verify_attempts=3)
    res = report.results[0]
    assert res.stop_reason == "check_failed"
    assert res.status == "failed"
    assert len(responder_events(tmp_path, "reflection")) == 2
    assert len(responder_events(tmp_path, "route")) == 3


@pytest.mark.slow
def test_verify_pinned_model_kept_with_escalation_on(tmp_path, scripted):
    cfg = cfg_cost()
    cfg = replace(
        cfg,
        escalation=replace(cfg.escalation, enabled=True, strong_model="mock/strong"),
    )
    task = visible_task(tmp_path / "e2e", "e2e_vpin")
    scripted.script[:] = [make_responder(["wrong", "right"])] * 60
    report = run_e2e(cfg, tmp_path, task, verify_attempts=2)
    res = report.results[0]
    assert ScriptedProvider.calls
    assert all(c.model == "mock/cheap" for c in ScriptedProvider.calls)
    assert all(e["model"] == "mock/cheap" for e in responder_events(tmp_path, "llm_call"))
    assert responder_events(tmp_path, "escalate") == []
    assert res.status == "solved"


@pytest.mark.slow
def test_verify_cost_cap_spans_attempts(tmp_path, scripted):
    M18cCostProvider.per_call = 0.05
    M18cCostProvider.after_reflection = None
    task = visible_task(tmp_path / "e2e", "e2e_vcap", **{"limits.cost_usd": 0.23})
    scripted.script[:] = [make_responder(["wrong", "wrong", "right"])] * 60
    report = asyncio.run(
        run_live_bench(
            cfg_cost(),
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.50,
            max_task_cost_usd=0.50,
            max_iterations=12,
            state_dir=tmp_path / "state",
            verify_attempts=3,
        )
    )
    res = report.results[0]
    calls = ScriptedProvider.calls
    idx = next(i for i, r in enumerate(calls) if r.messages[-1].content.startswith(REFLECT_PREFIX))
    in_attempt2 = len(calls) - idx - 1
    # Every call costs 0.05; the cap 0.23 is per task. Attempt 1 (>= 2 calls, >= 0.10) plus its
    # reflection (0.05) carry over, so attempt 2 hits the cap after 1-2 calls (0.25 >= 0.23) and
    # attempt 3, which would write "right" and solve, never starts. Attempt 2 alone spends at
    # most 0.10 (+ projection <= ~0.02), far below 0.23: a cap reset per attempt would not stop it.
    assert res.end_reason == "cost_limit"
    assert res.status == "stopped_budget"
    assert len(responder_events(tmp_path, "reflection")) == 1
    assert len(responder_events(tmp_path, "route")) == 2
    assert idx >= 2
    assert 1 <= in_attempt2 <= 2
    assert res.cost_usd == pytest.approx(0.05 * len(calls))
    stops = responder_events(tmp_path, "budget_trip") + responder_events(tmp_path, "budget_gate")
    assert len(stops) == 1
    t = stops[0]
    spent = t["used"]["cost_usd"] if t["type"] == "budget_trip" else t["spent_usd"]
    assert spent == pytest.approx(res.cost_usd)
    assert spent >= 0.20
    assert 0.05 * in_attempt2 <= 0.10
    assert report.settings["max_cost_usd"] == 0.50
    assert report.settings["max_task_cost_usd"] == 0.50
    if t["type"] == "budget_gate":
        assert t["spent_usd"] + t["projected_usd"] > 0.23
        assert t["spent_usd"] + t["projected_usd"] <= 0.50
    else:
        assert t["used"]["cost_usd"] >= 0.23


def _legacy_run_config(
    config: CoraConfig,
    model_id: str,
    protocol: str,
    max_iterations: int,
    max_task_cost: float,
    tool_groups=DEFAULT_BENCH_TOOL_GROUPS,
    sensor: bool = False,
) -> CoraConfig:
    cfg = apply_pin(config, model_id)
    models = tuple(dataclasses.replace(m, tool_protocol=None) for m in cfg.models)
    return dataclasses.replace(
        cfg,
        models=models,
        agent=dataclasses.replace(
            cfg.agent,
            approval="auto",
            max_iterations=max_iterations,
            max_attempts=1,
            max_cost_usd=max_task_cost,
            tool_protocol=protocol,
            tripwire=sensor,
            sensor_max_retries=AgentSettings().sensor_max_retries,
            sensor_feedback_chars=AgentSettings().sensor_feedback_chars,
            auto_check=False,
            selftest=False,
        ),
        delegation=dataclasses.replace(cfg.delegation, enabled=False),
        tool_groups=ToolGroupSettings(
            disabled=tuple(g for g in OPTIONAL_GROUPS if g not in tool_groups),
            auto_simple=False,
        ),
    )


def _two_model_cfg() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
                {
                    "id": "mock/strong",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


@pytest.mark.parametrize(
    "sensor, groups",
    [(False, DEFAULT_BENCH_TOOL_GROUPS), (True, ("core", "git"))],
)
def test_run_config_golden_without_flag(sensor, groups):
    cfg = _two_model_cfg()
    legacy = _legacy_run_config(cfg, "mock/cheap", "react", 7, 0.05, groups, sensor=sensor)
    assert _run_config(cfg, "mock/cheap", "react", 7, 0.05, groups, sensor=sensor) == legacy
    assert (
        _run_config(
            cfg, "mock/cheap", "react", 7, 0.05, groups, sensor=sensor, verify_attempts=None
        )
        == legacy
    )


def test_run_config_with_flag_changes_only_two_fields():
    cfg = _two_model_cfg()
    legacy = _legacy_run_config(cfg, "mock/cheap", "react", 7, 0.05)
    flagged = _run_config(cfg, "mock/cheap", "react", 7, 0.05, verify_attempts=3)
    expected = replace(legacy, agent=replace(legacy.agent, max_attempts=3, auto_check=True))
    assert flagged == expected

    cheap = next(m for m in cfg.models if m.id == "mock/cheap")
    base_arm = _arm_config(
        cfg, "deleg-off", cheap, None, "react", 7, 0.05, DEFAULT_BENCH_TOOL_GROUPS, False
    )
    flagged_arm = _arm_config(
        cfg,
        "deleg-off",
        cheap,
        None,
        "react",
        7,
        0.05,
        DEFAULT_BENCH_TOOL_GROUPS,
        False,
        verify_attempts=3,
    )
    assert flagged_arm == replace(
        base_arm, agent=replace(base_arm.agent, max_attempts=3, auto_check=True)
    )


def test_validate_verify_attempts(tmp_path):
    task = visible_task(tmp_path / "e2e", "e2e_vval")
    live = LiveTask("l1", "query", "q", {"f.txt": "x"}, answer_regex=r"\b42\b")
    for bad in (1, 6):
        with pytest.raises(ConfigError, match="from 2 to 5"):
            validate_verify_attempts(bad, sensor=False, tasks=[task])
    for bad in (True, "3"):
        with pytest.raises(ConfigError, match="from 2 to 5"):
            validate_verify_attempts(bad, sensor=False, tasks=[task])
    with pytest.raises(ConfigError, match="mutually exclusive"):
        validate_verify_attempts(3, sensor=True, tasks=[task])
    with pytest.raises(ConfigError, match="requires --suite e2e"):
        validate_verify_attempts(3, sensor=False, tasks=[live])
    with pytest.raises(ConfigError, match="requires --suite e2e"):
        validate_verify_attempts(3, sensor=False, tasks=[])
    validate_verify_attempts(None, sensor=False, tasks=[task])
    validate_verify_attempts(3, sensor=False, tasks=[task])


def test_settings_without_flag_have_no_verify_key(tmp_path, scripted):
    scripted.script[:] = ["Final Answer: 42"]
    live = LiveTask("q1", "query", "q", {"f.txt": "x"}, answer_regex=r"\b42\b")
    report = asyncio.run(
        run_live_bench(
            cfg_cost(),
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[live],
            max_cost_usd=0.30,
            max_task_cost_usd=0.10,
            max_iterations=4,
            state_dir=tmp_path / "state",
        )
    )
    assert "verify_attempts" not in report.settings
