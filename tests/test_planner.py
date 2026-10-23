from __future__ import annotations

import asyncio
import json

import pytest

from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.metering import CostMeter
from cora.core.milestones import (
    Condition,
    Milestone,
    PlanError,
    ProjectPlan,
    load_plan,
    plan_to_toml,
)
from cora.core.planner import (
    PLAN_DOC_KEYS,
    PlanBudgetExceeded,
    generate_plan,
    plan_error_outcome,
    plan_from_text,
    plan_messages,
    plan_outcome,
    plan_project,
)
from cora.core.types import CompletionResponse

VALID = {
    "goal": "g",
    "milestones": [
        {
            "id": "a",
            "title": "A",
            "task": "do a",
            "conditions": [
                {"kind": "command", "cmd": "true"},
                {"kind": "file_exists", "path": "out/x.txt"},
            ],
        },
        {"id": "b", "title": "B", "task": "do b", "check": "true"},
    ],
}


def test_plan_from_text_valid():
    plan = plan_from_text(json.dumps(VALID), max_milestones=8)
    assert [m.id for m in plan.milestones] == ["a", "b"]
    assert plan.milestones[0].conditions == (
        Condition("command", cmd="true"),
        Condition("file_exists", path="out/x.txt"),
    )
    assert plan.milestones[1].check == "true"


def test_plan_from_text_fenced():
    text = "Here:\n```json\n" + json.dumps(VALID) + "\n```\n"
    assert plan_from_text(text, max_milestones=8) == plan_from_text(
        json.dumps(VALID), max_milestones=8
    )


@pytest.mark.parametrize(
    "text, message",
    [
        ("{oops", "not valid JSON"),
        ("[]", "JSON object"),
        (json.dumps({**VALID, "goal": ""}), "'goal' must be a non-empty string"),
        (json.dumps({**VALID, "milestones": []}), "no milestones"),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {"id": f"m{i}", "title": "T", "task": "t"} for i in range(9)
                    ],
                }
            ),
            "too many milestones: 9 (max 8)",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {"id": "a", "title": "A", "task": "t"},
                        {"id": "a", "title": "A", "task": "t"},
                    ],
                }
            ),
            "duplicate id 'a'",
        ),
        (
            json.dumps({"goal": "g", "milestones": [{"id": "a", "title": "A", "task": " "}]}),
            "'task' is missing or empty",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {
                            "id": "a",
                            "title": "A",
                            "task": "t",
                            "conditions": [{"kind": "http", "url": "x"}],
                        }
                    ],
                }
            ),
            "unknown kind 'http'",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {"id": "a", "title": "A", "task": "t", "conditions": [{"kind": "command"}]}
                    ],
                }
            ),
            "'cmd' must be a non-empty string",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {
                            "id": "a",
                            "title": "A",
                            "task": "t",
                            "conditions": [{"kind": "file_exists", "path": "/etc/passwd"}],
                        }
                    ],
                }
            ),
            "relative to the workspace",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {
                            "id": "a",
                            "title": "A",
                            "task": "t",
                            "conditions": [{"kind": "file_exists", "path": "../x"}],
                        }
                    ],
                }
            ),
            "relative to the workspace",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {
                            "id": "a",
                            "title": "A",
                            "task": "t",
                            "conditions": [{"kind": "file_exists", "path": "a/../../x"}],
                        }
                    ],
                }
            ),
            "relative to the workspace",
        ),
        (
            json.dumps(
                {
                    "goal": "g",
                    "milestones": [
                        {
                            "id": "a",
                            "title": "A",
                            "task": "t",
                            "conditions": [
                                {"kind": "command", "cmd": "true", "shell": "sh"}
                            ],
                        }
                    ],
                }
            ),
            "unknown key 'shell'",
        ),
    ],
)
def test_plan_from_text_invalid(text, message):
    with pytest.raises(PlanError) as info:
        plan_from_text(text, max_milestones=8)
    assert message in str(info.value)


def test_plan_project_repair_once():
    calls: list[list] = []
    replies = iter(["nope", json.dumps(VALID)])

    async def call(msgs):
        calls.append(list(msgs))
        return next(replies)

    plan = asyncio.run(plan_project("g", call))
    assert [m.id for m in plan.milestones] == ["a", "b"]
    assert len(calls) == 2
    assert "not valid JSON" in calls[1][-1].content


def test_plan_project_invalid_twice():
    calls: list[list] = []
    replies = iter(["nope", "nope", json.dumps(VALID)])

    async def call(msgs):
        calls.append(list(msgs))
        return next(replies)

    with pytest.raises(PlanError) as info:
        asyncio.run(plan_project("g", call))
    assert "after one repair attempt" in str(info.value)
    assert "not valid JSON" in str(info.value)
    assert len(calls) == 2


def test_plan_messages_only_goal():
    msgs = plan_messages("build X", 8)
    assert len(msgs) == 2
    assert msgs[1].content == "Goal:\nbuild X"
    assert "8" in msgs[0].content


def test_plan_to_toml_roundtrip(tmp_path):
    plan = ProjectPlan(
        'q"uote\\ back\nline 한글 \x7f',
        (
            Milestone(
                "a",
                "A",
                "do\tthis\nthen that",
                "true",
                (Condition("command", cmd="echo hi"), Condition("file_exists", path="out/x.txt")),
            ),
            Milestone("b", "B", "do b"),
        ),
    )
    path = tmp_path / "plan.toml"
    path.write_text(plan_to_toml(plan), encoding="utf-8")
    assert load_plan(path) == plan


def test_generate_plan_metered(mock_config, scripted):
    scripted.script = [
        CompletionResponse(json.dumps(VALID), 100, 50, "mock/cheap", cost_usd=0.01)
    ]
    gov = BudgetGovernor(BudgetLimits(cost_usd=1.0, iterations=30, wall_s=None, tool_calls=None))
    meter = CostMeter()
    plan, info = asyncio.run(
        generate_plan("g", mock_config, gov, meter=meter, max_milestones=8)
    )
    assert [m.id for m in plan.milestones] == ["a", "b"]
    assert info["cost_usd"] == pytest.approx(0.01)
    assert info["calls"] == 1
    assert info["model"] == "mock/cheap"
    assert gov.usage().cost_usd == pytest.approx(0.01)
    assert scripted.calls[0].tools is None
    assert scripted.calls[0].messages[-1].content == "Goal:\ng"


def test_generate_plan_cost_cap(mock_config, scripted):
    gov = BudgetGovernor(BudgetLimits(cost_usd=0.0, iterations=30, wall_s=None, tool_calls=None))
    with pytest.raises(PlanBudgetExceeded) as info:
        asyncio.run(
            generate_plan("g", mock_config, gov, meter=CostMeter(), max_milestones=8)
        )
    assert info.value.cap == "cost"
    assert len(scripted.calls) == 0


def test_plan_outcome_keys(tmp_path):
    plan = ProjectPlan("g", (Milestone("a", "A", "do a"),))
    ok = plan_outcome(tmp_path / "plan.toml", plan, CostMeter(), None, wall_s=0)
    err = plan_error_outcome("x", 2, goal="g", meter=CostMeter(), governor=None, wall_s=0)
    assert set(ok) == set(PLAN_DOC_KEYS)
    assert set(err) == set(PLAN_DOC_KEYS)
