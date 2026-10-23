from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from cora.core.config import DEFAULT_GRADES, GRADES, TIERS, CoraConfig, RouterSettings, load_config
from cora.core.decider import group_question
from cora.core.deciders.heuristic import HeuristicDecider
from cora.core.router import HeuristicRouter, prompt_features, score_from_features
from cora.core.toolgroups import OPTIONAL_GROUPS, auto_hidden_groups, request_signals

ROOT = Path(__file__).resolve().parents[1]

PROMPTS = [
    "What is the capital of France?",
    "hi",
    "What is 2+2?",
    "Fix the failing test in src/calc.py: add() returns the wrong result",
    "calc.py의 버그를 수정하고 테스트를 통과시켜줘",
    "explain this function",
    "refactor the module",
    "look at README.md",
    "first read the docs, then summarize them",
    "1. list files\n 2. read them",
    "x" * 450,
    "please " * 80 + "fix it",
    "show the git log",
    "커밋해줘",
    "fetch https://example.com/page",
    "웹사이트 링크를 열어줘",
    "make a plan and a todo checklist",
    "단계별 계획을 세워줘",
    "delegate the search to a subagent",
    "하위 에이전트에게 위임해",
    "summarize @notes.md please",
    "```python\nprint(1)\n```",
    "그리고 다음에 정리해",
    "",
]

CONFIG_NAMES = ["mock", "repo", "tuned_router", "grade_model_id"]


def _configs(mock: CoraConfig) -> dict[str, CoraConfig]:
    return {
        "mock": mock,
        "repo": load_config(ROOT / "cora.toml"),
        "tuned_router": replace(
            mock,
            router=RouterSettings(
                threshold=5,
                medium_threshold=2,
                grades={**DEFAULT_GRADES, "medium": "strong"},
            ),
        ),
        "grade_model_id": replace(
            mock,
            router=RouterSettings(grades={**DEFAULT_GRADES, "complex": "mock/cheap"}),
        ),
    }


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("cfg_name", CONFIG_NAMES)
@pytest.mark.parametrize("prompt", PROMPTS)
def test_heuristic_matches_router(mock_config, cfg_name, prompt):
    cfg = _configs(mock_config)[cfg_name]
    router = HeuristicRouter(cfg)
    decider = HeuristicDecider(cfg)
    route = router.route(prompt)

    assert _run(decider.choice("tier", TIERS, text=prompt)).label == route.tier
    assert (
        _run(decider.choice("tier", TIERS, features=prompt_features(prompt))).label == route.tier
    )
    assert _run(decider.choice("grade", GRADES, text=prompt)).label == route.grade
    assert _run(decider.score("complexity", 0, 8, text=prompt)).value == router.score(prompt)[0]
    assert score_from_features(prompt_features(prompt)) == router.score(prompt)


@pytest.mark.parametrize("prompt", PROMPTS)
def test_heuristic_groups_match_regex(mock_config, prompt):
    decider = HeuristicDecider(mock_config)
    for plan_mode in (False, True):
        wanted: set[str] = set()
        for g in OPTIONAL_GROUPS:
            noul = _run(
                decider.noul(
                    group_question(g), text=prompt, features={"plan_mode": plan_mode}
                )
            )
            assert noul.yes == (g in request_signals(prompt, plan_mode=plan_mode))
            if noul.yes:
                wanted.add(g)
        kwargs = {
            "auto_simple": True,
            "grade": "simple",
            "text": prompt,
            "has_attachments": False,
            "plan_mode": plan_mode,
            "keep": set(),
        }
        assert auto_hidden_groups(**kwargs, wanted=wanted) == auto_hidden_groups(**kwargs)
