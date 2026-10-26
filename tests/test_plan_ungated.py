from __future__ import annotations

import tomllib

import pytest

from cora.core.config import ProjectSettings, parse_config
from cora.core.errors import ConfigError
from cora.core.milestones import (
    PROJECT_KEYS,
    Milestone,
    PlanError,
    ProjectPlan,
    new_checkpoint,
    parse_plan,
    plan_to_toml,
    project_error_outcome,
    project_outcome,
)

RUN_ID = "20261026-120000-abcdef"


def _config(project: dict | None = None):
    data: dict = {
        "models": [
            {
                "id": "m/cheap",
                "provider": "openrouter",
                "tier": "cheap",
                "input_usd_per_mtok": 0.2,
                "output_usd_per_mtok": 0.8,
            },
            {
                "id": "m/strong",
                "provider": "openrouter",
                "tier": "strong",
                "input_usd_per_mtok": 0.6,
                "output_usd_per_mtok": 2.5,
            },
        ]
    }
    if project is not None:
        data["project"] = project
    return parse_config(data)


def test_ungated_round_trip():
    plan = ProjectPlan(
        "goal",
        (Milestone("a", "t", "x", ungated=True), Milestone("b", "t", "x")),
    )
    text = plan_to_toml(plan)
    assert text.count("ungated = true") == 1
    assert "ungated" not in text.split("[[milestones]]")[2]
    parsed = parse_plan(tomllib.loads(text), "test")
    assert parsed.milestones[0].ungated is True
    assert parsed.milestones[1].ungated is False


def test_ungated_must_be_bool():
    data = {
        "goal": "g",
        "milestones": [{"id": "a", "title": "t", "task": "x", "ungated": "yes"}],
    }
    with pytest.raises(PlanError):
        parse_plan(data, "test")


def test_policy_repairs_config():
    assert _config().project.policy_repairs == 1
    assert ProjectSettings().policy_repairs == 1
    assert _config({"policy_repairs": 0}).project.policy_repairs == 0
    assert _config({"policy_repairs": 3}).project.policy_repairs == 3
    for bad in (-1, 4, True, "1"):
        with pytest.raises(ConfigError, match="policy_repairs"):
            _config({"policy_repairs": bad})


def test_unknown_project_key_rejected():
    with pytest.raises(ConfigError):
        _config({"no_such_key": 1})


def test_project_outcome_ungated_key():
    plan = ProjectPlan("goal", (Milestone("a", "t", "x", ungated=True), Milestone("b", "t", "x")))
    cp = new_checkpoint(RUN_ID, plan)
    doc = project_outcome(cp, None, stop_reason="final_answer", wall_s=0.0)
    assert doc["ungated_milestones"] == ["a"]
    assert set(doc) == set(PROJECT_KEYS)
    assert project_error_outcome("x")["ungated_milestones"] == []
