from __future__ import annotations

import asyncio
import logging

from conftest import COMPLEX_PROMPT
from cora.core.agent import Agent
from cora.core.observability import read_events
from cora.core.router import HeuristicRouter, score_from_features
from cora.core.tools import ApprovalPolicy


def test_simple_question_routes_cheap(mock_config):
    r = HeuristicRouter(mock_config).route("What is the capital of France?")
    assert r.tier == "cheap"


def test_ordinary_code_fix_routes_cheap(mock_config):
    r = HeuristicRouter(mock_config).route(
        "Fix the failing test in src/calc.py: add() returns the wrong result"
    )
    assert r.tier == "cheap"
    assert r.grade == "medium"
    assert "code_task_keywords" in r.reasons
    assert "code_reference" in r.reasons


def test_korean_code_fix_routes_cheap(mock_config):
    r = HeuristicRouter(mock_config).route("calc.py의 버그를 수정하고 테스트를 통과시켜줘")
    assert r.tier == "cheap"


def test_route_is_logged(caplog, mock_config):
    caplog.set_level(logging.INFO, logger="cora.router")
    HeuristicRouter(mock_config).route(COMPLEX_PROMPT)
    assert "tier=strong" in caplog.text
    assert "model=mock/strong" in caplog.text


def test_each_signal_weighs_one(mock_config):
    assert score_from_features(
        {"chars": 10, "code_keywords": True, "code_reference": True, "multi_step": False}
    ) == (2, ["code_task_keywords", "code_reference"])
    assert score_from_features(
        {"chars": 400, "code_keywords": True, "code_reference": True, "multi_step": True}
    ) == (4, ["long_prompt", "code_task_keywords", "code_reference", "multi_step"])
    assert HeuristicRouter(mock_config).route(COMPLEX_PROMPT).grade == "complex"


def test_agent_emits_route_event(scripted, mock_config, tmp_path):
    scripted.script[:] = ["Final Answer: Paris"]
    r = asyncio.run(
        Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run(
            "What is the capital of France?"
        )
    )
    routes = [e for e in read_events(r.log_path) if e["type"] == "route"]
    assert routes
    assert routes[0]["tier"] == "cheap"
