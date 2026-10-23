from __future__ import annotations

import asyncio

import pytest
from typer.testing import CliRunner

from conftest import COMPLEX_PROMPT, run_repl
from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.config import apply_pin, parse_config
from cora.core.errors import ConfigError
from cora.core.router import HeuristicRouter
from cora.core.tools import ApprovalPolicy


def _model(mid: str, tier: str, inp: float, out: float) -> dict:
    return {
        "id": mid,
        "provider": "scripted",
        "tier": tier,
        "input_usd_per_mtok": inp,
        "output_usd_per_mtok": out,
    }


def three_model_config(**router):
    return parse_config(
        {
            "models": [
                _model("mock/cheap", "cheap", 1, 2),
                _model("mock/strong", "strong", 5, 10),
                _model("mock/mid", "cheap", 2, 4),
            ],
            "router": {"grades": {"medium": "mock/mid"}, **router},
            "agent": {"approval": "auto"},
        }
    )


def test_grades_map_to_configured_models():
    r = HeuristicRouter(three_model_config())
    d = r.route("What is the capital of France?")
    assert d.grade == "simple"
    assert d.model.id == "mock/cheap"
    d = r.route("Summarize README.md")
    assert d.grade == "medium"
    assert d.model.id == "mock/mid"
    d = r.route(COMPLEX_PROMPT)
    assert d.grade == "complex"
    assert d.model.id == "mock/strong"


def test_threshold_configurable():
    cfg = three_model_config(threshold=6)
    d = HeuristicRouter(cfg).route("Fix the failing test in src/calc.py")
    assert d.grade == "medium"
    assert d.model.id == "mock/mid"


def test_agent_uses_grade_model(scripted, tmp_path):
    scripted.script.append("Final Answer: ok")
    asyncio.run(
        Agent(three_model_config(), tmp_path, ApprovalPolicy("auto")).run("Summarize README.md")
    )
    assert scripted.calls[0].model == "mock/mid"


def test_classifier_failure_falls_back(monkeypatch, mock_config):
    def boom(self, prompt):
        raise RuntimeError("x")

    monkeypatch.setattr(HeuristicRouter, "score", boom)
    d = HeuristicRouter(mock_config).route("Fix the bug in a.py")
    assert d.grade == "unknown"
    assert d.model.id == "mock/cheap"
    assert "classifier_error:RuntimeError" in d.reasons
    assert "fallback:default" in d.reasons


def test_classifier_failure_cli_exit0(monkeypatch, scripted, ws, cfg_file):
    def boom(self, prompt):
        raise RuntimeError("x")

    monkeypatch.setattr(HeuristicRouter, "score", boom)
    scripted.script.append("Final Answer: ok")
    result = CliRunner().invoke(
        app,
        ["run", "fix the bug in a.py", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
    )
    assert result.exit_code == 0
    assert scripted.calls[0].model == "mock/cheap"


def test_unresolved_grade_mapping_falls_back():
    cfg = parse_config(
        {
            "models": [_model("mock/cheap", "cheap", 1, 2), _model("mock/strong", "strong", 5, 10)],
            "router": {"grades": {"complex": "nope/x"}},
        }
    )
    d = HeuristicRouter(cfg).route(COMPLEX_PROMPT)
    assert d.model.id == "mock/cheap"
    assert "unresolved:nope/x" in d.reasons


def test_config_validation():
    minimal = {"models": [_model("mock/cheap", "cheap", 1, 2)]}
    bad = [
        {"router": {"grades": {"hard": "cheap"}}},
        {"router": {"medium_threshold": 5, "threshold": 3}},
        {"delegation": {"bogus": 1}},
        {"agent": {"max_parallel_tools": 0}},
    ]
    for extra in bad:
        with pytest.raises(ConfigError):
            parse_config({**minimal, **extra})
    cfg = parse_config(minimal)
    assert cfg.delegation.enabled is False
    assert cfg.agent.max_parallel_tools == 4
    assert cfg.router.grades == {"simple": "cheap", "medium": "cheap", "complex": "strong"}


def test_pin_overrides_every_grade(mock_config):
    cfg = apply_pin(mock_config, "foo/bar")
    r = HeuristicRouter(cfg)
    prompts = (
        "What is the capital of France?",
        "Summarize README.md",
        "Fix the failing test in src/calc.py",
    )
    for p in prompts:
        d = r.route(p)
        assert d.model.id == "foo/bar"
        assert "pinned:foo/bar" in d.reasons
    d = r.route("hello", force_tier="strong")
    assert d.model.id == "foo/bar"
    assert "pinned:foo/bar" in d.reasons
    same = apply_pin(mock_config, "mock/cheap")
    assert len(same.models) == 2
    complex_route = HeuristicRouter(same).route("Fix the failing test in src/calc.py")
    assert complex_route.model.id == "mock/cheap"


def test_repl_pin_and_unpin(scripted, ws, cfg_file):
    scripted.script.extend(["Final Answer: a", "Final Answer: b"])
    out = run_repl(
        ws,
        cfg_file,
        [
            "/model pin mock/cheap",
            "fix the bug in a.py",
            "/model pin",
            "/model unpin",
            COMPLEX_PROMPT,
            "/model pin a/b 1",
            "/exit",
        ],
    )
    assert scripted.calls[0].model == "mock/cheap"
    assert scripted.calls[1].model == "mock/strong"
    assert "pinned: mock/cheap" in out
    assert "price must be IN,OUT" in out


def test_repl_pin_unknown_model_any_grade(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: a")
    out = run_repl(ws, cfg_file, ["/model pin foo/bar", "hello", "/exit"])
    assert scripted.calls[0].model == "foo/bar"
    assert "warning: model 'foo/bar'" in out


def test_route_command_shows_decision(scripted, ws, cfg_file):
    scripted.script.extend(["Final Answer: x", "Final Answer: y"])
    out = run_repl(
        ws,
        cfg_file,
        ["/route", "fix the bug in a.py", "/route", "hello", "/route", "/exit"],
    )
    assert "No routing decision yet" in out
    assert "route: grade=medium tier=cheap model=mock/cheap score=2" in out
    assert "reason: code_task_keywords, code_reference" in out
    assert "route: grade=simple tier=cheap model=mock/cheap score=0" in out
    assert "reason: no complexity signals" in out


def test_route_in_verbose_and_print_mode(ws, cfg_file):
    out = run_repl(ws, cfg_file, ["hello", "/exit"], verbose=True)
    assert '"grade": "simple"' in out
    result = CliRunner().invoke(app, ["-p", "hello", "-w", str(ws), "-c", str(cfg_file)])
    assert "[route] grade=simple" in result.stderr
