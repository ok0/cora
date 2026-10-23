from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from conftest import act, native, run_repl, tc, with_agent
from cora.core.agent import Agent
from cora.core.config import ToolGroupSettings, load_config, parse_config
from cora.core.delegation import DelegateTool
from cora.core.errors import ConfigError
from cora.core.prompts import build_system_prompt
from cora.core.toolgroups import (
    GROUPS,
    TOOL_GROUPS,
    auto_hidden_groups,
    group_of,
    request_signals,
)
from cora.core.tools import ApprovalPolicy, ToolRegistry, ToolResult, Workspace, default_tools
from cora.core.tools.plan import SubmitPlanTool
from cora.core.tools.sizes import format_size_report, size_report

CORE = {"list_files", "read_file", "search", "edit_file", "write_file", "delete_file", "run_shell"}
GOLDEN_DESCRIBE = "c10eb0f74c78b9b749dc122fb8ceefd725f95db8880203849bbdbade087a36d3"
GOLDEN_SCHEMAS = "e1bf86806c0ba06d52ffbb7612ce0e9ffd74cbc9cb613e959b2416e1dd7dc9ab"
ALL_13 = [t.name for t in default_tools()]


def cfg_groups(cfg, **kw):
    return dataclasses.replace(cfg, tool_groups=ToolGroupSettings(**kw))


async def _dummy(task: str) -> ToolResult:
    return ToolResult(False, "unused")


def test_every_tool_in_exactly_one_group():
    tools = [*default_tools(), SubmitPlanTool(), DelegateTool(_dummy)]
    names = {t.name for t in tools}
    for n in names:
        assert group_of(n) in GROUPS, n
    assert set(TOOL_GROUPS) == names
    for g in GROUPS:
        assert any(group_of(n) == g for n in names), g
    assert {n for n, g in TOOL_GROUPS.items() if g == "core"} == CORE


def test_default_prompt_bytes_unchanged_react(mock_config, scripted, tmp_path):
    describe = ToolRegistry(default_tools()).describe()
    assert hashlib.sha256(describe.encode()).hexdigest() == GOLDEN_DESCRIBE
    assert len(describe) == 1847
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run("hi"))
    assert scripted.calls[0].messages[0].content == build_system_prompt(
        Workspace(tmp_path).root,
        ToolRegistry(default_tools()).describe(),
        [],
        "",
        parallel=True,
        protocol="react",
    )


def test_default_prompt_bytes_unchanged_native(mock_config, scripted, tmp_path):
    cfg = with_agent(mock_config, tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [native(text="done")]
    asyncio.run(agent.run("hi"))
    assert scripted.calls[0].tools == ToolRegistry(default_tools()).schemas()
    dumped = json.dumps(scripted.calls[0].tools)
    assert len(dumped) == 5931
    assert hashlib.sha256(dumped.encode()).hexdigest() == GOLDEN_SCHEMAS


def test_config_disables_groups_react_and_native(mock_config, scripted, tmp_path):
    cfg = cfg_groups(mock_config, disabled=("web", "git"))
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run("hi"))
    system = scripted.calls[0].messages[0].content
    assert "web_fetch" not in system
    assert "git_" not in system

    cfg = with_agent(cfg, tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [native(text="done")]
    asyncio.run(agent.run("hi"))
    names = {t["function"]["name"] for t in scripted.calls[-1].tools}
    assert "web_fetch" not in names
    assert not any(n.startswith("git_") for n in names)
    assert CORE <= names


def _minimal(tool_groups):
    return {
        "models": [
            {
                "id": "mock/cheap",
                "provider": "scripted",
                "tier": "cheap",
                "input_usd_per_mtok": 1.0,
                "output_usd_per_mtok": 2.0,
            }
        ],
        "tool_groups": tool_groups,
    }


def test_tool_groups_config_validation_and_repo_toml():
    with pytest.raises(ConfigError, match="core"):
        parse_config(_minimal({"disabled": ["core"]}))
    with pytest.raises(ConfigError, match=r"\[tool_groups\]"):
        parse_config(_minimal({"disabled": ["nope"]}))
    with pytest.raises(ConfigError):
        parse_config(_minimal({"auto_simple": "yes"}))
    assert load_config(Path("cora.toml")).tool_groups == ToolGroupSettings((), True)
    assert parse_config(_minimal({})).tool_groups == ToolGroupSettings()


def test_repl_tools_command(scripted, ws, cfg_file):
    before = cfg_file.read_bytes()
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(
        ws,
        cfg_file,
        ["/tools", "/tools web off", "/tools core off", "/tools bogus on", "hello", "/exit"],
    )
    for g in ("core", "git", "web", "plan-todo", "delegate"):
        assert g in out
    assert "chars react" in out
    assert "chars schema" in out
    assert "the core group is always on and cannot be disabled" in out
    assert "unknown tool group" in out
    system = scripted.calls[0].messages[0].content
    assert "web_fetch" not in system
    assert "- git_status:" in system
    assert cfg_file.read_bytes() == before


def test_disabled_group_call_rejected_react(mock_config, scripted, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    cfg = cfg_groups(mock_config, disabled=("web",))
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [act("web_fetch", {"url": "https://example.com"}), "Final Answer: ok"]
    asyncio.run(agent.run("hi"))
    result = scripted.calls[1].messages[-1].content
    assert "tool group 'web', which is disabled" in result
    assert "/tools web on" in result
    assert "unknown tool" not in result


def test_disabled_group_call_rejected_native(mock_config, scripted, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    cfg = with_agent(cfg_groups(mock_config, disabled=("web",)), tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [
        native(tc("web_fetch", {"url": "https://example.com"})),
        native(text="ok"),
    ]
    asyncio.run(agent.run("hi"))
    result = next(m.content for m in scripted.calls[1].messages if m.role == "tool")
    assert "tool group 'web', which is disabled" in result
    assert "/tools web on" in result
    assert "unknown tool" not in result


def test_simple_auto_rule_core_only(mock_config, scripted, tmp_path):
    cfg = cfg_groups(mock_config, auto_simple=True)
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run("hi"))
    system = scripted.calls[0].messages[0].content
    assert "- list_files:" in system
    for line in ("- git_status:", "- web_fetch:", "- todo_write:"):
        assert line not in system

    cfg = with_agent(cfg, tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [native(text="done")]
    asyncio.run(agent.run("hi"))
    assert {t["function"]["name"] for t in scripted.calls[-1].tools} == CORE


@pytest.mark.parametrize(
    ("task", "attachments", "plan_mode", "forced", "present", "absent"),
    [
        ("fix the bug in calc.py", "", False, (), ALL_13, []),
        ("show the git log", "", False, (), ["git_log"], ["web_fetch"]),
        ("fetch https://example.com/page", "", False, (), ["web_fetch"], ["git_status"]),
        ("hi", "", True, (), ["todo_write", "submit_plan"], ["git_status"]),
        ("hi", "\n\n[a.txt]\nx", False, (), ALL_13, []),
        ("hi", "", False, ("git",), ["git_status"], ["web_fetch"]),
    ],
)
def test_auto_rule_signals_include_groups(
    mock_config, scripted, tmp_path, task, attachments, plan_mode, forced, present, absent
):
    cfg = cfg_groups(mock_config, auto_simple=True)
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = plan_mode
    agent.ctx.forced_groups = frozenset(forced)
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run(task, attachments=attachments))
    system = scripted.calls[0].messages[0].content
    for name in present:
        assert f"- {name}:" in system, name
    for name in absent:
        assert f"- {name}:" not in system, name


def test_hidden_tool_call_auto_enables_react(mock_config, scripted, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    cfg = cfg_groups(mock_config, auto_simple=True)
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [act("git_status", {}), "Final Answer: ok"]
    r = asyncio.run(agent.run("hi"))
    assert "- git_status:" not in scripted.calls[0].messages[0].content
    result = scripted.calls[1].messages[-1].content
    assert "belongs to the tool group 'git', which was not loaded" in result
    assert "not inside a git repository" in result
    assert not result.startswith("unknown tool")
    assert "- git_status:" in scripted.calls[1].messages[0].content
    assert "git" in r.session.tool_groups


def test_hidden_tool_call_auto_enables_native(mock_config, scripted, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    cfg = with_agent(cfg_groups(mock_config, auto_simple=True), tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [native(tc("git_status", {})), native(text="ok")]
    r = asyncio.run(agent.run("hi"))
    assert "git_status" not in {t["function"]["name"] for t in scripted.calls[0].tools}
    result = next(m.content for m in scripted.calls[1].messages if m.role == "tool")
    assert "belongs to the tool group 'git', which was not loaded" in result
    assert "not inside a git repository" in result
    assert "git_status" in {t["function"]["name"] for t in scripted.calls[1].tools}
    assert "git" in r.session.tool_groups


def test_size_report_numbers():
    rows = size_report()
    assert [(s.describe_chars, s.schema_chars) for _, s in rows] == [
        (1948, 6227),
        (1847, 5931),
        (980, 2829),
        (980, 2829),
    ]
    assert rows[2][1].describe_chars < rows[0][1].describe_chars
    assert rows[3][1].schema_chars < rows[0][1].schema_chars
    text = format_size_report(rows)
    for needle in ("1948", "980", "49.7%", "54.6%"):
        assert needle in text


def test_request_signals_unit():
    assert request_signals("commit this") == {"git"}
    assert "git" in request_signals("커밋해줘")
    assert "web" in request_signals("see http://x.y")
    assert "plan-todo" in request_signals("hello", plan_mode=True)
    assert request_signals("hello") == frozenset()
    assert (
        auto_hidden_groups(
            auto_simple=True,
            grade="medium",
            text="hi",
            has_attachments=False,
            plan_mode=False,
            keep=(),
        )
        == set()
    )
