from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, FIXED_CFG_TOML, PY, act
from cora.cli import project as project_mod
from cora.cli.main import app
from cora.core.milestones import PROJECT_KEYS, RUN_ID_RE
from cora.core.observability import read_events
from cora.core.tools.registry import ToolRegistry

THREE = [
    {"id": "m1", "title": "one", "task": "alpha-task"},
    {"id": "m2", "title": "two", "task": "beta-task"},
    {"id": "m3", "title": "three", "task": "gamma-task"},
]


def run_cli(args):
    return CliRunner().invoke(app, args)


def pdoc(result) -> dict:
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    d = json.loads(result.stdout)
    assert set(d) == set(PROJECT_KEYS)
    assert d["exit_code"] == result.exit_code
    return d


def write_plan(tmp_path: Path, ms: list[dict], name: str = "plan.toml") -> Path:
    lines = ['goal = "ship"']
    for m in ms:
        lines.append("[[milestones]]")
        for k, v in m.items():
            lines.append(f"{k} = {json.dumps(v, ensure_ascii=False)}")
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_cfg(tmp_path: Path, text: str, name: str = "cora.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def cp_json(ws: Path, run_id: str) -> dict:
    path = ws / ".cora" / "projects" / run_id / "checkpoint.json"
    return json.loads(path.read_text(encoding="utf-8"))


def task_calls(scripted, marker: str) -> int:
    count = 0
    for req in scripted.calls:
        first = next((m.content for m in req.messages if m.role == "user"), "")
        if marker in first:
            count += 1
    return count


def base(ws: Path, cfg: Path) -> list[str]:
    return ["-w", str(ws), "-c", str(cfg)]


def events(ws: Path, sid: str) -> list[dict]:
    return read_events(ws / ".cora" / "sessions" / sid / "events.jsonl")


def statuses(d: dict) -> list[str]:
    return [m["status"] for m in d["milestones"]]


def test_run_three_completed(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 0
    assert statuses(d) == ["completed", "completed", "completed"]
    assert len({m["session_id"] for m in d["milestones"]}) == 3
    assert RUN_ID_RE.fullmatch(d["run_id"])
    cp = cp_json(ws, d["run_id"])
    assert cp["completed"] == ["m1", "m2", "m3"]
    assert cp["current"] is None
    assert "project run id:" in result.stderr


def test_resume_completed_no_calls(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    first = pdoc(run_cli([
        "project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file),
    ]))
    n = len(scripted.calls)
    result = run_cli([
        "project", "resume", first["run_id"], "--headless", "--json", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    assert len(scripted.calls) == n
    assert d["final_answer"] == first["final_answer"]
    assert statuses(d) == ["completed", "completed", "completed"]


def test_resume_unknown_and_corrupt(scripted, ws, cfg_file, tmp_path):
    result = run_cli([
        "project", "resume", "20990101-000000-abcdef", "--headless", "--json", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert "project run not found" in d["errors"][0]
    assert d["run_id"] is None

    plan = write_plan(tmp_path, THREE)
    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    first = pdoc(run_cli([
        "project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file),
    ]))
    path = ws / ".cora" / "projects" / first["run_id"] / "checkpoint.json"
    path.write_text("{not json", encoding="utf-8")
    result = run_cli([
        "project", "resume", first["run_id"], "--headless", "--json", *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert "unreadable" in d["errors"][0]

    plain = run_cli(["project", "resume", "20990101-000000-abcdef", *base(ws, cfg_file)])
    assert plain.exit_code == 2
    assert "error:" in plain.stderr


def test_cumulative_tool_calls_then_resume(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend([act("list_files", {}), "Final Answer: x"] * 3)
    result = run_cli([
        "project", "run", str(plan), "--headless", "--json", "--max-tool-calls", "2",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 4
    assert d["stop_reason"] == "budget_exceeded"
    assert d["budget"]["tripped"] == "tool_calls"
    assert d["budget"]["used"]["tool_calls"] == 2 == sum(d["tools"].values())
    assert statuses(d) == ["completed", "completed", "failed"]
    assert d["budget"]["used"]["cost_usd"] == pytest.approx(d["cost_usd"])

    alpha_before = task_calls(scripted, "alpha-task")
    beta_before = task_calls(scripted, "beta-task")
    scripted.script[:] = [act("list_files", {}), "Final Answer: z"]
    result = run_cli([
        "project", "resume", d["run_id"], "--headless", "--json", "--max-tool-calls", "10",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    assert statuses(d) == ["completed", "completed", "completed"]
    assert d["budget"]["used"]["tool_calls"] == 3
    assert task_calls(scripted, "alpha-task") == alpha_before
    assert task_calls(scripted, "beta-task") == beta_before


@pytest.mark.parametrize(
    "flags,cfg_text,script,statuses_expected,cap,clock",
    [
        pytest.param(
            ["--max-iterations", "5"], CFG_TOML,
            [act("list_files", {}), "Final Answer: x"] * 3,
            ["completed", "completed", "failed"], "iterations", False,
            id="iterations",
        ),
        pytest.param(
            ["--max-tool-calls", "5"], CFG_TOML,
            [act("list_files", {})] * 20,
            ["failed", "pending", "pending"], "tool_calls", False,
            id="tool_calls",
        ),
        pytest.param(
            ["--max-cost", "0.02"], FIXED_CFG_TOML,
            [act("list_files", {})] * 20,
            ["failed", "pending", "pending"], "cost", False,
            id="cost",
        ),
        pytest.param(
            ["--max-wall-s", "250"], CFG_TOML,
            [act("list_files", {})] * 20,
            None, "wall", True,
            id="wall",
        ),
    ],
)
def test_project_caps(scripted, ws, tmp_path, monkeypatch, flags, cfg_text, script,
                      statuses_expected, cap, clock):
    if clock:
        monkeypatch.setattr(project_mod, "_clock", itertools.count(0, 100).__next__)
    cfg = write_cfg(tmp_path, cfg_text)
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend(script)
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *flags,
                      *base(ws, cfg)])
    d = pdoc(result)
    assert result.exit_code == 4
    assert d["stop_reason"] == "budget_exceeded"
    assert d["budget"]["tripped"] == cap
    if statuses_expected is not None:
        assert statuses(d) == statuses_expected
    if cap == "cost":
        assert d["budget"]["used"]["cost_usd"] <= 0.02 + 0.0012 + 1e-9


def test_check_failed_then_resume(scripted, ws, cfg_file, tmp_path):
    check = f"{PY} -c \"import os,sys; sys.exit(0 if os.path.exists('flag.txt') else 1)\""
    ms = [THREE[0], {**THREE[1], "check": check}, THREE[2]]
    plan = write_plan(tmp_path, ms)
    scripted.script.extend(["Final Answer: A", "Final Answer: B"])
    result = run_cli([
        "project", "run", str(plan), "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "check_failed"
    assert statuses(d) == ["completed", "failed", "pending"]

    (ws / "flag.txt").write_text("ok", encoding="utf-8")
    scripted.script.extend(["Final Answer: B2", "Final Answer: C"])
    result = run_cli([
        "project", "resume", d["run_id"], "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    assert statuses(d) == ["completed", "completed", "completed"]
    assert task_calls(scripted, "alpha-task") == 1


def test_check_passes_uses_sensor_gate(scripted, ws, cfg_file, tmp_path):
    ms = [{**THREE[0], "check": f"{PY} -c \"pass\""}, *THREE[1:]]
    plan = write_plan(tmp_path, ms)
    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    result = run_cli([
        "project", "run", str(plan), "--approval", "auto", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 0
    sid = d["milestones"][0]["session_id"]
    checks = [e for e in events(ws, sid) if e["type"] == "check"]
    assert any(e.get("sensor") is True and e.get("ok") is True for e in checks)


def test_policy_blocked_check(scripted, ws, cfg_file, tmp_path):
    ms = [THREE[0], {**THREE[1], "check": "curl http://example.invalid"}, THREE[2]]
    plan = write_plan(tmp_path, ms)
    scripted.script.extend(["Final Answer: A", "Final Answer: B"])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 5
    assert d["stop_reason"] == "policy_blocked"
    assert statuses(d)[2] == "pending"


def test_headless_semantics(scripted, ws, cfg_file, tmp_path, monkeypatch):
    plan = write_plan(tmp_path, THREE)
    result = run_cli([
        "project", "run", str(plan), "--approval", "ask", "--headless", "--json",
        *base(ws, cfg_file),
    ])
    d = pdoc(result)
    assert result.exit_code == 2
    assert d["run_id"] is None
    assert not (ws / ".cora" / "projects").exists()

    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", "-q",
                      *base(ws, cfg_file)])
    pdoc(result)
    assert result.stderr == ""

    original = ToolRegistry._execute_tool

    async def noisy(self, tool, name, args, ctx):
        print("STRAY")
        return await original(self, tool, name, args, ctx)

    monkeypatch.setattr(ToolRegistry, "_execute_tool", noisy)
    scripted.script.extend([act("list_files", {}), "Final Answer: A", "Final Answer: B",
                            "Final Answer: C"])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", "--approval", "auto",
                      *base(ws, cfg_file)])
    pdoc(result)
    assert "STRAY" in result.stderr


def test_credentials_protected_in_project(scripted, ws, tmp_path, monkeypatch, no_network):
    key = "sk-or-v1-" + "a" * 40
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    cfg = write_cfg(tmp_path, CFG_TOML)
    plan = write_plan(tmp_path, [{"id": "m1", "title": "one", "task": "q"}])
    (ws / ".env").write_text("TOKEN=topsecret-1", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core] topsecret-2", encoding="utf-8")
    before = {p: p.read_text("utf-8") for p in (ws / ".env", ws / ".git" / "config")}
    scripted.script.extend([
        act("read_file", {"path": ".env"}),
        act("search", {"pattern": "topsecret", "path": ".env"}),
        act("list_files", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .env"}),
        act("read_file", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .git/config"}),
        "Final Answer: done",
    ])
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg)])
    d = pdoc(result)
    assert result.exit_code == 0
    assert d["policy"]["deny"] + d["policy"]["ask_resolved_deny"] >= 5
    checkpoint_text = (ws / ".cora" / "projects" / d["run_id"] / "checkpoint.json").read_text(
        encoding="utf-8")
    for text in (result.stdout, result.stderr, checkpoint_text):
        assert "topsecret-" not in text
        assert key not in text
    sid = d["milestones"][0]["session_id"]
    for e in events(ws, sid):
        if e["type"] == "tool_call":
            assert "topsecret-" not in str(e.get("output_head", ""))
    assert {p: p.read_text("utf-8") for p in before} == before


@pytest.mark.parametrize(
    "name,text,problem",
    [
        ("missing", None, "plan file not found"),
        ("bad_toml", "goal = \n[[milestones]]\n", "bad TOML"),
        ("empty", 'goal = "g"\nmilestones = []\n', "no milestones"),
        (
            "duplicate",
            'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "a"\ntask = "x"\n'
            '[[milestones]]\nid = "m1"\ntitle = "b"\ntask = "y"\n',
            "duplicate id 'm1'",
        ),
        (
            "missing_task",
            'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "a"\n',
            "'task' is missing or empty",
        ),
        (
            "wrong_type",
            'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = 5\ntask = "x"\n',
            "'title' must be a string",
        ),
        (
            "conditions",
            'goal = "g"\n[[milestones]]\nid = "m1"\ntitle = "a"\ntask = "x"\n'
            'conditions = "x"\n',
            "'conditions' must be an array of tables",
        ),
    ],
)
def test_plan_validation_cli(scripted, ws, cfg_file, tmp_path, name, text, problem):
    if text is None:
        plan = tmp_path / "absent.toml"
    else:
        plan = tmp_path / f"{name}.toml"
        plan.write_text(text, encoding="utf-8")
    result = run_cli(["project", "run", str(plan), "--headless", "--json", *base(ws, cfg_file)])
    d = pdoc(result)
    assert result.exit_code == 2
    assert problem in d["errors"][0]
    assert not (ws / ".cora" / "projects").exists()


def test_non_headless_plain(scripted, ws, cfg_file, tmp_path):
    plan = write_plan(tmp_path, THREE)
    scripted.script.extend(["Final Answer: A", "Final Answer: B", "Final Answer: C"])
    result = run_cli(["project", "run", str(plan), "--approval", "auto", *base(ws, cfg_file)])
    assert result.exit_code == 0
    assert "C" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_help_lists_project():
    result = run_cli(["project", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "resume" in result.stdout
    top = run_cli(["--help"])
    assert "project" in top.stdout
