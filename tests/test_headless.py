from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, FIXED_CFG_TOML, act
from cora.cli import headless as headless_mod
from cora.cli.main import app
from cora.core.errors import ProviderAccountError
from cora.core.observability import read_events
from cora.core.outcome import OUTCOME_KEYS
from cora.core.providers import register_provider
from cora.core.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]


@register_provider("account_fail")
class AccountFailProvider:
    def __init__(self, settings) -> None:
        pass

    async def complete(self, req):
        raise ProviderAccountError(402, "insufficient credits", provider="openrouter")


def run_cli(args, input=None):
    return CliRunner().invoke(app, args, input=input)


def doc(result) -> dict:
    assert result.stdout.endswith("\n")
    assert result.stdout.count("\n") == 1
    d = json.loads(result.stdout)
    assert set(d) == set(OUTCOME_KEYS)
    assert d["exit_code"] == result.exit_code
    return d


def events(ws: Path, sid: str) -> list[dict]:
    return read_events(ws / ".cora" / "sessions" / sid / "events.jsonl")


def session_json(ws: Path, sid: str) -> dict:
    return json.loads((ws / ".cora" / "sessions" / sid / "session.json").read_text("utf-8"))


def base(ws: Path, cfg: Path) -> list[str]:
    return ["-w", str(ws), "-c", str(cfg)]


def write_cfg(tmp_path: Path, text: str, name: str = "cora.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def fake_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(headless_mod, "_clock", itertools.count(0, 100).__next__)


def test_final_answer_json(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: 42")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 0
    assert d["ok"] is True
    assert d["stop_reason"] == "final_answer"
    assert d["final_answer"] == "42"
    assert d["policy"]["mode"] == "policy"
    assert d["budget"]["limits"]["wall_s"] == 900
    assert d["budget"]["limits"]["tool_calls"] == 200
    assert d["models"] == ["mock/cheap"]
    assert d["tokens"]["in"] > 0


def test_stray_print_goes_to_stderr(scripted, ws, cfg_file, monkeypatch):
    original = ToolRegistry._execute_tool

    async def noisy(self, tool, name, args, ctx):
        print("STRAY")
        return await original(self, tool, name, args, ctx)

    monkeypatch.setattr(ToolRegistry, "_execute_tool", noisy)
    (ws / "a.txt").write_text("hello", encoding="utf-8")
    scripted.script.extend([
        act("list_files", {}),
        act("list_files", {}),
        act("read_file", {"path": "a.txt"}),
        "Final Answer: ok",
    ])
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert "STRAY" in result.stderr
    assert d["tools"] == {"list_files": 2, "read_file": 1}


def test_check_failed_exit_1(scripted, ws, cfg_file):
    scripted.script.extend(["Final Answer: x", "reflection", "Final Answer: x"])
    result = run_cli([
        "run", "q", "--headless", "--json", "--approval", "auto", "--check", "false",
        *base(ws, cfg_file),
    ])
    d = doc(result)
    assert result.exit_code == 1
    assert d["stop_reason"] == "check_failed"
    lines = [ln for ln in result.stderr.splitlines() if ln.startswith("warning: --approval auto")]
    assert len(lines) == 1


@pytest.mark.parametrize(
    "snippet,key",
    [
        ("max_wall_s = -1", "max_wall_s"),
        ('max_tool_calls = "x"', "max_tool_calls"),
        ("budget_warn_fraction = 0", "budget_warn_fraction"),
        ("budget_warn_fraction = 1.5", "budget_warn_fraction"),
        ("budget_warn_fraction = -0.1", "budget_warn_fraction"),
        ('lenient_parse = "yes"', "lenient_parse"),
    ],
)
def test_invalid_config_exit_2(tmp_path, ws, snippet, key):
    cfg = write_cfg(tmp_path, CFG_TOML + f"\n[agent]\n{snippet}\n")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert d["exit_code"] == 2
    assert key in d["errors"][0]

    plain = run_cli(["run", "q", "--headless", *base(ws, cfg)])
    assert plain.exit_code == 2
    assert "error: invalid [agent]." in plain.stderr
    assert plain.stdout == ""


def test_invalid_cli_cap_exit_2(ws, cfg_file):
    result = run_cli([
        "run", "q", "--max-wall-s", "-1", "--headless", "--json", *base(ws, cfg_file),
    ])
    d = doc(result)
    assert result.exit_code == 2
    assert "--max-wall-s" in d["errors"][0]


def test_missing_key_exit_2(no_network, ws):
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, REPO_ROOT / "cora.toml")])
    d = doc(result)
    assert result.exit_code == 2
    assert "OPENROUTER_API_KEY" in d["errors"][0]


def test_provider_account_error_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML.replace('provider = "scripted"',
                                               'provider = "account_fail"'))
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["errors"]
    assert d["session_id"]


CAP_CASES = [
    pytest.param(["--max-iterations", "3"], CFG_TOML, 10, "iterations", "max_iterations",
                 False, id="iterations"),
    pytest.param(["--max-tool-calls", "2"], CFG_TOML, 10, "tool_calls", "budget_exceeded",
                 False, id="tool_calls"),
    pytest.param(["--max-cost", "0.005"], FIXED_CFG_TOML, 20, "cost", "cost_limit",
                 False, id="cost"),
    pytest.param(["--max-wall-s", "250"], CFG_TOML, 10, "wall", "budget_exceeded",
                 True, id="wall"),
]


@pytest.mark.parametrize("flags,cfg_text,n,cap,raw,clock", CAP_CASES)
def test_budget_caps(scripted, ws, tmp_path, monkeypatch, flags, cfg_text, n, cap, raw, clock):
    if clock:
        fake_clock(monkeypatch)
    cfg = write_cfg(tmp_path, cfg_text)
    scripted.script.extend([act("list_files", {})] * n)
    result = run_cli(["run", "q", "--headless", "--json", *flags, *base(ws, cfg)])
    d = doc(result)
    assert result.exit_code == 4
    assert d["stop_reason"] == "budget_exceeded"
    assert d["budget"]["tripped"] == cap
    assert d["budget"]["used"]
    stored = session_json(ws, d["session_id"])
    assert stored["stop_reason"] == raw
    if cap == "iterations":
        assert len(scripted.calls) == 3
    elif cap == "tool_calls":
        assert d["budget"]["used"]["tool_calls"] == 2
        assert len(scripted.calls) == 3
    elif cap == "cost":
        assert d["budget"]["used"]["cost_usd"] <= 0.005 + 0.0012 + 1e-9
    else:
        assert len(scripted.calls) <= 2


@pytest.mark.parametrize(
    "flags,cfg_text,n,cap,clock",
    [
        pytest.param(["--max-iterations", "5"], CFG_TOML, 20, "iterations", False,
                     id="iterations"),
        pytest.param(["--max-tool-calls", "5"], CFG_TOML, 20, "tool_calls", False,
                     id="tool_calls"),
        pytest.param(
            ["--max-cost", "0.02"],
            FIXED_CFG_TOML + "\n[agent]\nreact_max_tokens = 1024\n",
            20, "cost", False, id="cost",
        ),
        pytest.param(["--max-wall-s", "250"], CFG_TOML, 20, "wall", True, id="wall"),
    ],
)
def test_warning_once_per_cap(scripted, ws, tmp_path, monkeypatch, flags, cfg_text, n, cap,
                              clock):
    if clock:
        fake_clock(monkeypatch)
    cfg = write_cfg(tmp_path, cfg_text)
    scripted.script.extend([act("list_files", {})] * n)
    result = run_cli(["run", "q", "--headless", "--json", *flags, *base(ws, cfg)])
    d = doc(result)
    lines = [ln for ln in result.stderr.splitlines() if ln.startswith(f"warning: budget {cap}")]
    assert len(lines) == 1
    matching = [w for w in d["warnings"] if cap in w]
    assert len(matching) == 1
    warn_events = [e for e in events(ws, d["session_id"]) if e["type"] == "budget_warning"]
    assert len([e for e in warn_events if e["cap"] == cap]) == 1
    assert d["budget"]["warned"] is True


def test_no_warning_below_fraction(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert d["warnings"] == []
    assert d["budget"]["warned"] is False
    assert not [e for e in events(ws, d["session_id"]) if e["type"] == "budget_warning"]


def test_subagent_usage_counts(scripted, ws, cfg_file):
    scripted.script.extend([
        act("delegate", {"task": "list"}),
        act("list_files", {}),
        "Final Answer: SUB",
        "Final Answer: done",
    ])
    result = run_cli(["run", "q", "--headless", "--json", "--delegate", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 0
    assert d["tools"] == {"delegate": 1, "list_files": 1}
    assert d["budget"]["used"]["tool_calls"] == 2
    assert d["cost_usd"] > 0
    assert abs(d["cost_usd"] - d["budget"]["used"]["cost_usd"]) < 1e-12


def test_subagent_trip_stops_parent(scripted, ws, cfg_file):
    scripted.script.extend([act("delegate", {"task": "list"})] + [act("list_files", {})] * 10)
    result = run_cli([
        "run", "q", "--headless", "--json", "--delegate", "--max-tool-calls", "2",
        *base(ws, cfg_file),
    ])
    d = doc(result)
    assert result.exit_code == 4
    assert d["budget"]["tripped"] == "tool_calls"
    assert d["budget"]["used"]["tool_calls"] == 2


def test_task_sources_equal(scripted, ws, cfg_file, tmp_path):
    task_file = tmp_path / "task.md"
    task_file.write_text("do it\n", encoding="utf-8")
    runs = [
        (["run", "do it", "--headless", "--json", *base(ws, cfg_file)], None),
        (["run", "--task-file", str(task_file), "--headless", "--json", *base(ws, cfg_file)],
         None),
        (["run", "-", "--headless", "--json", *base(ws, cfg_file)], "do it\n"),
    ]
    answers = []
    for args, stdin in runs:
        scripted.script.append("Final Answer: same")
        start = len(scripted.calls)
        result = run_cli(args, input=stdin)
        d = doc(result)
        answers.append(d["final_answer"])
        first = scripted.calls[start]
        assert any("Task: do it" in m.content for m in first.messages)
    assert answers == ["same", "same", "same"]


@pytest.mark.parametrize(
    "case",
    ["no_task", "task_and_file", "empty_file", "whitespace_stdin", "missing_file"],
)
def test_task_source_errors(scripted, ws, cfg_file, tmp_path, case):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    missing = tmp_path / "missing.md"
    common = ["--headless", "--json", *base(ws, cfg_file)]
    if case == "no_task":
        args, stdin = ["run", *common], None
    elif case == "task_and_file":
        args, stdin = ["run", "q", "--task-file", str(empty), *common], None
    elif case == "empty_file":
        args, stdin = ["run", "--task-file", str(empty), *common], None
    elif case == "whitespace_stdin":
        args, stdin = ["run", "-", *common], "  \n"
    else:
        args, stdin = ["run", "--task-file", str(missing), *common], None
    result = run_cli(args, input=stdin)
    d = doc(result)
    assert result.exit_code == 2
    assert d["errors"]


def test_approval_rules(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    assert doc(result)["policy"]["mode"] == "policy"

    result = run_cli([
        "run", "q", "--approval", "ask", "--headless", "--json", *base(ws, cfg_file),
    ])
    d = doc(result)
    assert result.exit_code == 2
    assert "--approval ask" in d["errors"][0]


def test_ask_rule_denied_and_counted(scripted, ws, cfg_file, no_network):
    scripted.script.extend([act("web_fetch", {"url": "https://example.com"}), "Final Answer: ok"])
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 0
    assert d["policy"]["ask_resolved_deny"] == 1


def test_policy_blocked_exit_5(scripted, ws, cfg_file):
    scripted.script.extend(["Final Answer: done", "reflection", "Final Answer: done"])
    result = run_cli([
        "run", "q", "--headless", "--json", "--check", "curl http://example.invalid",
        *base(ws, cfg_file),
    ])
    d = doc(result)
    assert result.exit_code == 5
    assert d["stop_reason"] == "policy_blocked"
    assert d["policy"]["deny"] >= 1
    assert d["policy"]["decisions"]


def test_credentials_protected(scripted, ws, cfg_file, no_network):
    (ws / ".env").write_text("TOKEN=topsecret-1", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core] topsecret-2", encoding="utf-8")
    before = {p: p.read_text("utf-8") for p in (ws / ".env", ws / ".git" / "config")}
    git = shutil.which("git")

    def repo_status() -> str:
        return subprocess.run(
            [git, "-C", str(REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout

    status_before = repo_status() if git else None
    scripted.script.extend([
        act("read_file", {"path": ".env"}),
        act("search", {"pattern": "topsecret", "path": ".env"}),
        act("list_files", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .env"}),
        act("read_file", {"path": ".git/config"}),
        act("run_shell", {"command": "cat .git/config"}),
        "Final Answer: done",
    ])
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 0
    assert d["policy"]["deny"] >= 5
    assert "topsecret-" not in result.stdout
    assert "topsecret-" not in result.stderr
    for e in events(ws, d["session_id"]):
        if e["type"] == "tool_call":
            assert "topsecret-" not in str(e.get("output_head", ""))
    assert {p: p.read_text("utf-8") for p in before} == before
    if git:
        assert repo_status() == status_before


def test_quiet_stderr_empty(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    result = run_cli(["run", "q", "--headless", "--json", "-q", *base(ws, cfg_file)])
    assert doc(result)["ok"] is True
    assert result.stderr == ""


def test_quiet_keeps_errors_and_warnings(scripted, ws, cfg_file, tmp_path):
    scripted.script.append("Final Answer: x")
    result = run_cli(["run", "q", "-q", "--headless", "--approval", "auto", *base(ws, cfg_file)])
    assert any(ln.startswith("warning: --approval auto") for ln in result.stderr.splitlines())

    bad = write_cfg(tmp_path, CFG_TOML + "\n[agent]\nmax_wall_s = -1\n", "bad.toml")
    result = run_cli(["run", "q", "-q", "--headless", "--json", *base(ws, bad)])
    assert "error:" in result.stderr


def test_resume_cost_cumulative(scripted, ws, tmp_path):
    cfg = write_cfg(tmp_path, FIXED_CFG_TOML)
    scripted.script.append("Final Answer: one")
    first = doc(run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)]))
    sid = first["session_id"]
    c1 = first["cost_usd"]
    calls_before = len(scripted.calls)
    scripted.script.extend([act("list_files", {})] * 5)
    result = run_cli([
        "run", "--headless", "--json", "--resume", sid, "follow up",
        "--max-cost", str(c1 + 0.0005), *base(ws, cfg),
    ])
    d = doc(result)
    assert result.exit_code == 4
    assert d["budget"]["tripped"] == "cost"
    assert d["budget"]["used"]["cost_usd"] >= c1
    assert len(scripted.calls) == calls_before


def test_resume_without_task(scripted, ws, cfg_file):
    scripted.script.extend([act("list_files", {})] * 3)
    first = doc(run_cli([
        "run", "q", "--headless", "--json", "--max-iterations", "1", *base(ws, cfg_file),
    ]))
    assert first["exit_code"] == 4
    sid = first["session_id"]
    scripted.script.append("Final Answer: done")
    result = run_cli([
        "run", "--headless", "--json", "--resume", sid, "--max-iterations", "5",
        *base(ws, cfg_file),
    ])
    assert doc(result)["exit_code"] == 0
    assert result.exit_code == 0


def test_resume_unknown_id(ws, cfg_file):
    result = run_cli(["run", "--headless", "--json", "--resume", "nope", *base(ws, cfg_file)])
    d = doc(result)
    assert result.exit_code == 2
    assert "session not found" in d["errors"][0]


def test_resume_requires_headless(ws, cfg_file):
    result = run_cli(["run", "t", "--json", "--resume", "x", *base(ws, cfg_file)])
    assert result.exit_code == 2


def test_headless_defaults_and_override(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    d = doc(run_cli(["run", "q", "--headless", "--json", *base(ws, cfg_file)]))
    assert d["budget"]["limits"]["wall_s"] == 900
    assert d["budget"]["limits"]["tool_calls"] == 200

    scripted.script.append("Final Answer: x")
    d = doc(run_cli([
        "run", "q", "--headless", "--json", "--max-tool-calls", "7", "--max-wall-s", "60",
        *base(ws, cfg_file),
    ]))
    assert d["budget"]["limits"]["tool_calls"] == 7
    assert d["budget"]["limits"]["wall_s"] == 60

    scripted.script.append("Final Answer: x")
    d = doc(run_cli(["run", "q", "--json", *base(ws, cfg_file)]))
    limits = d["budget"]["limits"]
    assert limits["wall_s"] is None
    assert limits["tool_calls"] is None
    assert limits["cost_usd"] == 0.5
    assert limits["iterations"] == 30


def test_default_run_unchanged(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: 42")
    result = run_cli(["run", "what", "--approval", "auto", *base(ws, cfg_file)])
    assert result.exit_code == 0
    assert result.stdout == "42\n"
    assert "stop_reason: final_answer" in result.stderr
    assert "== CORA cost summary ==" in result.stderr
    assert "session: " in result.stderr
    for line in result.stderr.splitlines():
        assert "budget" not in line
        assert not line.startswith("warning")


def test_json_without_headless_one_document(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    result = run_cli(["run", "x", "--json", "--approval", "auto", *base(ws, cfg_file)])
    assert doc(result)["ok"] is True
    assert result.exit_code == 0


def test_print_headless(scripted, ws, cfg_file):
    scripted.script.append("Final Answer: x")
    result = run_cli(["-p", "x", "--headless", "--json", *base(ws, cfg_file)])
    assert doc(result)["ok"] is True


def test_nonheadless_tool_cap_exit_1(scripted, ws, cfg_file):
    scripted.script.extend([act("list_files", {})] * 5)
    result = run_cli([
        "run", "x", "--approval", "auto", "--max-tool-calls", "1", *base(ws, cfg_file),
    ])
    assert result.exit_code == 1
    assert "stop_reason: budget_exceeded" in result.stderr
    assert "budget exceeded: tool_calls" in result.stderr
