from __future__ import annotations

import asyncio
import json

import pytest

from cora.core.milestones import PlanError
from cora.core.planner import lenient_plan_json, plan_from_text, plan_project
from test_planner import VALID
from test_project_plan_cli import base, plandoc, run_cli

pytestmark = pytest.mark.usefixtures("no_network")

PLAIN = json.dumps(VALID)
PRETTY = json.dumps(VALID, indent=2)


def _trailing_comma() -> str:
    s = PRETTY
    i = s.rfind("]")
    s = s[:i] + "," + s[i:]
    j = s.rfind("}")
    return s[:j] + "," + s[j:]


ROWS = [
    ("fenced_no_lang", "```\n" + PLAIN + "\n```", ("strip_fences",)),
    (
        "noise_around",
        "Sure! Here is the plan:\n" + PLAIN + "\nHope this helps.",
        ("extract_object",),
    ),
    ("trailing_comma", _trailing_comma(), ("trailing_commas",)),
    ("single_quotes", PLAIN.replace('"', "'"), ("single_quotes",)),
    (
        "fence_noise_comma",
        "Here:\n```json\n" + _trailing_comma() + "\n```\nThanks.",
        ("strip_fences", "extract_object", "trailing_commas"),
    ),
]

M14_UNTERMINATED = PRETTY[: PRETTY.index('"task": "do b') + len('"task": "do b')]


@pytest.mark.parametrize(("row_id", "text", "expected"), ROWS, ids=[r[0] for r in ROWS])
def test_lenient_table(row_id, text, expected):
    r = lenient_plan_json(text)
    assert r is not None
    assert r[0] == VALID
    assert r[1] == expected
    assert plan_from_text(text, max_milestones=8, lenient=True) == plan_from_text(
        PLAIN, max_milestones=8
    )


@pytest.mark.parametrize(("row_id", "text", "expected"), ROWS, ids=[r[0] for r in ROWS])
def test_strict_mode_unchanged(row_id, text, expected):
    if row_id == "fenced_no_lang":
        assert plan_from_text(text, max_milestones=8) == plan_from_text(PLAIN, max_milestones=8)
        return
    with pytest.raises(PlanError, match="not valid JSON"):
        plan_from_text(text, max_milestones=8)


@pytest.mark.parametrize("text", [PLAIN, PRETTY])
def test_valid_json_identical(text):
    assert plan_from_text(text, max_milestones=8, lenient=True) == plan_from_text(
        text, max_milestones=8, lenient=False
    )


def test_m14_unterminated_still_invalid():
    assert lenient_plan_json(M14_UNTERMINATED) is None
    with pytest.raises(PlanError, match="not valid JSON: Unterminated string"):
        plan_from_text(M14_UNTERMINATED, max_milestones=8, lenient=True)


def test_plan_project_lenient_saves_repair():
    calls = []

    async def call(msgs):
        calls.append(msgs)
        return PLAIN.replace('"', "'")

    plan = asyncio.run(plan_project("g", call, lenient=True))
    assert [m.id for m in plan.milestones] == ["a", "b"]
    assert len(calls) == 1


def test_plan_project_m14_shape_after_repair():
    calls = []
    replies = [M14_UNTERMINATED, M14_UNTERMINATED]

    async def call(msgs):
        calls.append(msgs)
        return replies[len(calls) - 1]

    with pytest.raises(PlanError) as info:
        asyncio.run(plan_project("g", call, lenient=True))
    assert "after one repair attempt" in str(info.value)
    assert "Unterminated string" in str(info.value)
    assert len(calls) == 2


def test_cli_plan_m14_shape_exit_2(scripted, ws, cfg_file):
    scripted.script.extend([M14_UNTERMINATED, M14_UNTERMINATED, "unused"])
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    d = plandoc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert "Unterminated string" in d["errors"][0]
    assert not out.exists()
    assert len(scripted.calls) == 2


def test_cli_plan_trailing_comma_one_call(scripted, ws, cfg_file):
    scripted.script.append(_trailing_comma())
    out = ws / "plan.toml"
    result = run_cli(["project", "plan", "g", "-o", str(out), "--json", *base(ws, cfg_file)])
    plandoc(result)
    assert result.exit_code == 0
    assert len(scripted.calls) == 1
    assert out.exists()
