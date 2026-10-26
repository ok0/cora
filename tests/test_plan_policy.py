from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.metering import CostMeter
from cora.core.milestones import PlanError
from cora.core.planner import (
    POLICY_RULES_HEADER,
    generate_plan,
    plan_from_text,
    plan_project,
    validate_plan_policy,
)
from cora.core.policy import RULE_HINTS, PolicySettings, hint_for, planning_policy


@pytest.fixture
def pol(tmp_path: Path):
    return planning_policy(PolicySettings(), tmp_path, "policy")


def milestone(mid: str, check: str | None = None, conds=()) -> dict:
    m: dict = {"id": mid, "title": "T", "task": "do it"}
    if check is not None:
        m["check"] = check
    if conds:
        m["conditions"] = list(conds)
    return m


def plan_json(*milestones: dict) -> str:
    return json.dumps({"goal": "g", "milestones": list(milestones)})


def replies_call(replies, calls: list):
    it = iter(replies)

    async def call(msgs):
        calls.append(list(msgs))
        return next(it)

    return call


def test_prompt_carries_rules(pol, tmp_path):
    reply = plan_json(milestone("m1", "ls"))
    with_calls: list = []
    asyncio.run(plan_project("g", replies_call([reply], with_calls), policy=pol))
    system = with_calls[0][0].content
    assert POLICY_RULES_HEADER in system
    assert "Allowed commands" in system

    plain_calls: list = []
    asyncio.run(plan_project("g", replies_call([reply], plain_calls)))
    plain = plain_calls[0][0].content
    assert POLICY_RULES_HEADER not in plain
    assert "Allowed commands" not in plain


def test_validate_flags_denied_only(pol):
    plan = plan_from_text(
        plan_json(
            milestone("m1", "cd src && ls"),
            milestone("m2", "ls"),
            milestone("m3", conds=[{"kind": "command", "cmd": "python -c 'print(1)'"}]),
        ),
        max_milestones=8,
    )
    issues = validate_plan_policy(plan, pol)
    assert [(i.milestone_id, i.field, i.command, i.rule) for i in issues] == [
        ("m1", "check", "cd src && ls", "confine:cd"),
        ("m3", "conditions[0]", "python -c 'print(1)'", "confine:one-liner"),
    ]
    assert issues[0].hint == hint_for(pol.verdict("cd src && ls"))
    assert issues[1].hint == hint_for(pol.verdict("python -c 'print(1)'"))


def test_validate_ask_follows_mode(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".cora").mkdir(parents=True)
    (ws / ".cora" / "policy.toml").write_text(
        '[[rules]]\nid = "mk"\ndecision = "ask"\ntool = "run_shell"\ncommand = "make *"\n',
        encoding="utf-8",
    )
    plan = plan_from_text(plan_json(milestone("m1", "make x")), max_milestones=8)
    policy_pol = planning_policy(PolicySettings(), ws, "policy")
    assert policy_pol is not None
    assert [i.rule for i in validate_plan_policy(plan, policy_pol)] == ["mk"]

    confine_ws = tmp_path / "confine"
    confine_ws.mkdir()
    ask_pol = planning_policy(PolicySettings(shell_confinement=True), confine_ws, "ask")
    assert ask_pol is not None
    ls_plan = plan_from_text(plan_json(milestone("m1", "ls")), max_milestones=8)
    assert validate_plan_policy(ls_plan, ask_pol) == []


def test_repair_round_names_command_rule_hint(pol):
    calls: list = []
    events: list[dict] = []
    call = replies_call(
        [plan_json(milestone("m1", "cd src && ls")), plan_json(milestone("m1", "ls"))], calls
    )
    plan = asyncio.run(plan_project("g", call, policy=pol, on_policy=events.append))
    assert len(calls) == 2
    last = calls[1][-1].content
    assert "cd src && ls" in last
    assert "confine:cd" in last
    assert RULE_HINTS["confine:cd"].text in last
    assert plan.milestones[0].check == "ls"
    assert events == [
        {
            "issues": 1,
            "repaired": 1,
            "dropped": 0,
            "rounds": 1,
            "ungated": [],
            "policy_dropped": [],
        }
    ]


def test_still_denied_is_dropped(pol):
    calls: list = []
    events: list[dict] = []
    denied = plan_json(milestone("m1", "cd src && ls"))
    plan = asyncio.run(
        plan_project(
            "g",
            replies_call([denied, denied], calls),
            policy=pol,
            policy_repairs=1,
            on_policy=events.append,
        )
    )
    assert len(calls) == 2
    assert plan.milestones[0].check is None
    assert len(events) == 1
    assert events[0]["policy_dropped"] == [
        {"milestone": "m1", "field": "check", "command": "cd src && ls", "rule": "confine:cd"}
    ]


def test_repairs_zero_no_model_call(pol):
    calls: list = []
    events: list[dict] = []
    plan = asyncio.run(
        plan_project(
            "g",
            replies_call([plan_json(milestone("m1", "cd src && ls"))], calls),
            policy=pol,
            policy_repairs=0,
            on_policy=events.append,
        )
    )
    assert len(calls) == 1
    assert plan.milestones[0].check is None
    assert events[0]["dropped"] == 1


def test_ungated_flagged(pol):
    calls: list = []
    events: list[dict] = []
    reply = plan_json(
        milestone("m1", "cd src && ls"),
        milestone("m2", "cd x && ls", conds=[{"kind": "command", "cmd": "ls"}]),
    )
    plan = asyncio.run(
        plan_project(
            "g",
            replies_call([reply], calls),
            policy=pol,
            policy_repairs=0,
            on_policy=events.append,
        )
    )
    m1, m2 = plan.milestones
    assert m1.ungated is True
    assert m2.ungated is False
    assert m2.conditions and m2.conditions[0].cmd == "ls"
    assert events[0]["ungated"] == ["m1"]


def test_invalid_repair_reply_keeps_previous_plan(pol):
    calls: list = []
    events: list[dict] = []
    plan = asyncio.run(
        plan_project(
            "g",
            replies_call([plan_json(milestone("m1", "cd src && ls")), "nope"], calls),
            policy=pol,
            policy_repairs=1,
            on_policy=events.append,
        )
    )
    assert len(calls) == 2
    assert [m.id for m in plan.milestones] == ["m1"]
    assert plan.milestones[0].check is None
    assert events[0]["dropped"] == 1


def test_model_cannot_set_ungated(pol):
    reply_with_flag = json.dumps(
        {"goal": "g", "milestones": [{"id": "m1", "title": "T", "task": "t", "ungated": True}]}
    )
    with pytest.raises(PlanError, match="unknown key 'ungated'"):
        plan_from_text(reply_with_flag, max_milestones=8)

    calls: list = []
    plan = asyncio.run(
        plan_project(
            "g",
            replies_call([reply_with_flag, plan_json(milestone("m1", "ls"))], calls),
            policy=pol,
        )
    )
    assert len(calls) == 2
    assert "unknown key 'ungated'" in calls[1][-1].content
    assert plan.milestones[0].ungated is False


def test_generate_plan_info_policy(mock_config, scripted, pol):
    denied = plan_json(milestone("m1", "cd src && ls"))
    scripted.script = [denied, denied, plan_json(milestone("m1", "ls"))]
    gov = BudgetGovernor(BudgetLimits(cost_usd=1.0, iterations=30, wall_s=None, tool_calls=None))
    _, info = asyncio.run(
        generate_plan("g", mock_config, gov, meter=CostMeter(), max_milestones=8, policy=pol)
    )
    assert info["policy"]["dropped"] == 1
    assert info["policy"]["policy_dropped"][0]["rule"] == "confine:cd"

    _, plain_info = asyncio.run(
        generate_plan("g", mock_config, gov, meter=CostMeter(), max_milestones=8)
    )
    assert plain_info["policy"] is None
