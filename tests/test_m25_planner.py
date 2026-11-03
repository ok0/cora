from __future__ import annotations

import asyncio
import json
import re

import pytest

import m20_trial
from conftest import CFG_TOML
from cora.core.config import load_config
from cora.core.milestones import Milestone, PlanError, ProjectPlan, load_plan
from cora.core.planner import (
    GOAL_PATHS_RULE,
    PLAN_RULES,
    PLANNER_SYSTEM,
    REPAIR_HINTS,
    SELECTOR_HINT,
    SELECTOR_RULE,
    UNDERIVED_HINT,
    UNDERIVED_RULE,
    classify_reply,
    plan_from_text,
    plan_messages,
    plan_project,
    validate_plan_paths,
    validate_plan_policy,
    workspace_listing,
    workspace_test_names,
)
from cora.core.policy import planning_policy
from m20_trial import ROOT
from m25_diag import _prepared
from test_project_cli import base, run_cli, write_cfg
from test_project_plan_cli import VALID

FIX = ROOT / "tests/fixtures/m25"
CONFIG = ROOT / "tests/fixtures/m20/artifacts/cora-m20-deepseek.toml"
N08_R2 = (
    ROOT
    / "tests/fixtures/m20d/artifacts/m20d-deepseek-v2/e2e_n08-r2/projects"
    / "20261028-120515-c7c46f/plan.toml"
)
PJ = json.dumps(load_plan(N08_R2).to_dict())
ERR = "model reply is not valid JSON: Expecting value (line 1, column 1)"
REL_N08_R2 = N08_R2.relative_to(ROOT).as_posix()
EXCEPTION = (
    "tests/fixtures/m20/artifacts/v2/e2e_h01-r0/projects/20261025-215255-bbc53e/plan.toml",
    "m5",
    "conditions[0]",
)


def _jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (FIX / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fake(replies: list[str]):
    seen: list[list] = []
    queue = iter(replies)

    async def call(msgs):
        seen.append(list(msgs))
        return next(queue)

    return call, seen


def _check_plan(command: str) -> ProjectPlan:
    return ProjectPlan(
        goal="g",
        milestones=(Milestone(id="m1", title="t", task="x", check=command),),
    )


def _rules(command: str, goal: str = "g", existing=(), tests=()) -> list[str]:
    issues = validate_plan_paths(_check_plan(command), goal, list(existing), list(tests))
    return [i.rule for i in issues]


def test_scan_objects_prose_with_braces():
    text = "Plan for {the goal} below.\n" + PJ + "\nDone {ok}."
    assert plan_from_text(text, max_milestones=8, lenient=True) == plan_from_text(
        PJ, max_milestones=8
    )


def test_scan_objects_think_tag():
    text = "<think>try {a: 1}</think>\n" + PJ
    assert plan_from_text(text, max_milestones=8, lenient=True) == plan_from_text(
        PJ, max_milestones=8
    )


def test_non_plan_unchanged():
    with pytest.raises(PlanError, match=r"not valid JSON: Expecting value \(line 1, column 1\)"):
        plan_from_text("I cannot help with that.", max_milestones=8, lenient=True)


@pytest.mark.parametrize(
    ("text", "error", "finish", "expected"),
    [
        ("", ERR, None, "empty"),
        (PJ[:200], ERR, None, "truncated"),
        ("no braces", ERR, None, "no_object"),
        ("Here:\n" + PJ + "\nbye", ERR, None, "prose_or_fence"),
        (PJ, "model reply: 'goal' must be a non-empty string", None, "schema"),
        (PJ, ERR, "length", "truncated"),
    ],
)
def test_classify_reply(text, error, finish, expected):
    assert classify_reply(text, error, finish) == expected


def test_repair_hint_off_identical():
    call, seen = _fake(["", PJ])
    asyncio.run(plan_project("g", call, max_milestones=8, repair_hint=False))
    assert seen[1][-1].content == (
        f"Your reply was invalid: {ERR}\nReply again with only the corrected JSON object."
    )


def test_repair_hint_on():
    call, seen = _fake(["", PJ])
    asyncio.run(plan_project("g", call, max_milestones=8, repair_hint=True))
    assert REPAIR_HINTS["empty"] in seen[1][-1].content


def test_goal_paths_flags_invented_files():
    expected = {
        (r["milestone"], r["field"])
        for r in _jsonl("refcheck.jsonl")
        if r["plan"] == REL_N08_R2 and not r["pass_ref"]
    }
    _, ws = _prepared("e2e_n08")
    issues = validate_plan_paths(
        load_plan(N08_R2), m20_trial.goal_text("e2e_n08"), workspace_listing(ws)
    )
    assert {(i.milestone_id, i.field) for i in issues} == expected
    assert all(i.command != "contacts/normalize.py" for i in issues)


def test_goal_paths_repair_then_drop():
    plan_text = json.dumps({
        "goal": "g",
        "milestones": [{
            "id": "m1",
            "title": "t",
            "task": "x",
            "conditions": [{"kind": "file_exists", "path": "tests/new_test.py"}],
        }],
    })
    call, seen = _fake([plan_text, plan_text])
    payloads: list[dict] = []
    plan = asyncio.run(plan_project(
        "edit contacts/normalize.py",
        call,
        policy=None,
        workspace_files=["contacts/normalize.py"],
        on_policy=payloads.append,
    ))
    assert len(seen) == 2
    assert seen[1][-1].content.startswith(
        "Some checks or conditions in your plan cannot be used:\n"
    )
    assert plan.milestones[0].conditions == ()
    assert payloads[0]["path_issues"] == 1
    assert payloads[0]["dropped"] == 1


def test_goal_paths_keeps_goal_named_and_existing():
    goal = "write report.csv from contacts/normalize.py"
    plan_text = json.dumps({
        "goal": "g",
        "milestones": [{
            "id": "m1",
            "title": "t",
            "task": "x",
            "conditions": [
                {"kind": "file_exists", "path": "contacts/normalize.py"},
                {"kind": "file_exists", "path": "report.csv"},
                {"kind": "file_exists", "path": "contacts/"},
            ],
        }],
    })
    plan = plan_from_text(plan_text, max_milestones=8)
    assert validate_plan_paths(plan, goal, ["contacts/normalize.py"]) == []
    call, seen = _fake([plan_text])
    out = asyncio.run(plan_project(
        goal, call, policy=None, workspace_files=["contacts/normalize.py"],
    ))
    assert len(seen) == 1
    assert len(out.milestones[0].conditions) == 3


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("python3 run_tests.py", [UNDERIVED_RULE]),
        ("python3 -m unittest tests.test_normalize", [UNDERIVED_RULE]),
        ("python3 -m unittest tests.test_x", []),
        ("python -m contacts.cli", []),
        ("python -m pytest -q escapes/test_jsonstr.py::test_decode", [UNDERIVED_RULE]),
        ("python -m pytest -q tests/test_x.py::test_a", []),
        ("python3.11 -m pytest -q", []),
        ("curl -k https://example.org/x", []),
    ],
)
def test_goal_paths_bare_and_nodeid(command, expected):
    assert _rules(command, existing=["contacts/cli.py", "tests/test_x.py"]) == expected


def test_goal_paths_selector_rule(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_parse_simple():\n    pass\n", encoding="utf-8"
    )
    existing = ["tests/test_a.py"]
    names = workspace_test_names(tmp_path, existing)
    assert names == ["tests/test_a.py", "tests/test_a.py::test_parse_simple"]

    flagged = validate_plan_paths(
        _check_plan("python -m pytest -q -k parse_csv"), "g", existing, names
    )
    assert [i.rule for i in flagged] == [SELECTOR_RULE]
    assert flagged[0].hint.endswith("(existing tests: test_parse_simple)")
    assert flagged[0].hint.startswith(SELECTOR_HINT)

    assert _rules("python -m pytest -q -k test_main", existing=existing, tests=names) == [
        SELECTOR_RULE
    ]
    assert _rules("python -m pytest -q -k parse_simple", existing=existing, tests=names) == []
    assert _rules("python -m pytest -q -k 'test_a'", existing=existing, tests=names) == []
    assert _rules('python -m pytest -q -k "not slow"', existing=existing, tests=names) == []
    assert _rules("python -m pytest -q -kparse_simple", existing=existing, tests=names) == []
    assert _rules("sort -k 2 tests/test_a.py", existing=existing, tests=names) == []
    assert (
        _rules(
            "python -m pytest -q -k parse_csv",
            goal="add test_parse_csv to tests/test_a.py",
            existing=existing,
            tests=names,
        )
        == []
    )
    no_tests = validate_plan_paths(_check_plan("python -m pytest -q -k anything"), "g", [], ())
    assert [i.rule for i in no_tests] == [SELECTOR_RULE]
    assert no_tests[0].hint.endswith("(no tests exist yet)")


def test_goal_paths_all_reference_failures():
    rows = _jsonl("refcheck.jsonl")
    classes = {
        (r["plan"], r["milestone"], r["field"]): r["class"]
        for r in _jsonl("refcheck_classes.jsonl")
    }
    considered = [r for r in rows if not r["output_head"].startswith("denied by policy")]
    failing = {(r["plan"], r["milestone"], r["field"]) for r in considered if not r["pass_ref"]}
    passing = {(r["plan"], r["milestone"], r["field"]) for r in considered if r["pass_ref"]}
    tasks = {r["plan"]: r["task"] for r in considered}

    flagged: dict[tuple[str, str, str], str] = {}
    for plan_rel, task in sorted(tasks.items()):
        _, ws = _prepared(task)
        files = workspace_listing(ws)
        issues = validate_plan_paths(
            load_plan(ROOT / plan_rel),
            m20_trial.goal_text(task),
            files,
            workspace_test_names(ws, files),
        )
        for i in issues:
            flagged[(plan_rel, i.milestone_id, i.field)] = i.rule

    denied = {
        (r["plan"], r["milestone"], r["field"])
        for r in rows
        if r["output_head"].startswith("denied by policy")
    }
    not_denied = {key for key in flagged if key not in denied}
    assert not_denied == failing - {EXCEPTION}
    assert not set(flagged) & passing
    for key, cls in classes.items():
        if cls == "over_specified":
            assert flagged[key] == UNDERIVED_RULE, key
        if cls == "wrong_path_or_name":
            assert flagged[key] == SELECTOR_RULE, key
    assert all(rule in PLAN_RULES for rule in flagged.values())


def test_goal_paths_selector_repair_then_drop(tmp_path):
    plan_text = json.dumps({
        "goal": "g",
        "milestones": [{
            "id": "m1",
            "title": "t",
            "task": "x",
            "check": "python -m pytest -q -k parse_csv",
        }],
    })
    call, seen = _fake([plan_text, plan_text])
    payloads: list[dict] = []
    plan = asyncio.run(plan_project(
        "g",
        call,
        policy=None,
        workspace_files=["tests/test_a.py"],
        workspace_tests=["tests/test_a.py", "tests/test_a.py::test_parse_simple"],
        on_policy=payloads.append,
    ))
    assert len(seen) == 2
    last = seen[1][-1].content
    assert last.startswith("Some checks or conditions in your plan cannot be used:\n")
    assert SELECTOR_RULE in last
    assert plan.milestones[0].check is None
    assert payloads[0]["path_issues"] == 1


def test_goal_paths_off_no_listing(scripted, ws, cfg_file):
    (ws / "contacts").mkdir()
    (ws / "contacts" / "normalize.py").write_text("x", encoding="utf-8")
    scripted.script.append(json.dumps(VALID))
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "plan.toml"), "--json", *base(ws, cfg_file),
    ])
    assert result.exit_code == 0
    sent = scripted.calls[0].messages
    expected = plan_messages("g", load_config(cfg_file).project.max_milestones)
    assert [m.content for m in sent] == [m.content for m in expected]
    assert "Files already in the workspace" not in sent[-1].content


def test_goal_paths_on_listing(scripted, ws, tmp_path):
    (ws / "contacts").mkdir()
    (ws / "contacts" / "normalize.py").write_text("x", encoding="utf-8")
    cfg = write_cfg(
        tmp_path, CFG_TOML + "\n[project]\ngoal_paths = true\n", name="goal_paths.toml",
    )
    scripted.script.append(json.dumps(VALID))
    result = run_cli([
        "project", "plan", "g", "-o", str(ws / "plan.toml"), "--json", *base(ws, cfg),
    ])
    assert result.exit_code == 0
    sent = scripted.calls[0].messages
    assert "Files already in the workspace:\n" in sent[-1].content
    assert "contacts/normalize.py" in sent[-1].content
    assert GOAL_PATHS_RULE in sent[0].content
    assert PLANNER_SYSTEM.format(max=8) in sent[0].content


def test_m20_planner_checks_flagged():
    cfg = load_config(CONFIG)
    rows = [r for r in _jsonl("denials.jsonl") if r["id"] in ("D1", "D2", "D3", "D4")]
    assert len(rows) == 4
    for row in rows:
        events = ROOT / row["cite"].rsplit(":", 1)[0]
        run_dir = events.parents[2]
        task_id = re.sub(r"-r\d+$", "", run_dir.name)
        plan_path = next(run_dir.glob("projects/*/plan.toml"))
        _, ws = _prepared(task_id)
        policy = planning_policy(cfg.policy, ws, "policy")
        issues = validate_plan_policy(load_plan(plan_path), policy)
        assert any(i.command.startswith(row["command"]) for i in issues), row["id"]


def test_language_neutral_new_text():
    pattern = re.compile(
        r"\b(python\d*|pypy|pytest|node(js)?|npm|deno|bun|ruby|perl|php|lua|rscript|"
        r"javascript|typescript|java|rust|cargo|bash|zsh|pwsh|powershell)\b",
        re.I,
    )
    texts = [GOAL_PATHS_RULE, UNDERIVED_HINT, SELECTOR_HINT, *REPAIR_HINTS.values()]
    assert all(pattern.search(t) is None for t in texts)
