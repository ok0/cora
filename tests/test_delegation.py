from __future__ import annotations

import asyncio
import dataclasses
import tomllib

from typer.testing import CliRunner

from conftest import FIXED_CFG_TOML, act, with_agent, write_files
from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.config import DelegationSettings, parse_config
from cora.core.errors import ProviderError
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy, ToolResult, default_tools


def deleg(cfg, **kw):
    return dataclasses.replace(cfg, delegation=DelegationSettings(enabled=True, **kw))


class SlowTool:
    name = "slow"
    description = "t"
    args_doc = "{}"
    requires_approval = False
    read_only = True

    def preflight(self, args, ctx):
        return None

    async def run(self, args, ctx):
        await asyncio.sleep(1)
        return ToolResult(True, "slow")


def boom(req):
    raise ProviderError("boom")


def test_delegate_isolated_summary_only(tmp_path, mock_config, scripted):
    write_files(tmp_path, {"zzz_marker.txt": "x"})
    cfg = deleg(mock_config, max_per_session=1)
    scripted.script.extend(
        [
            act("delegate", {"task": "list the files and summarize"}),
            act("list_files", {}),
            "Final Answer: SUBSUMMARY two files",
            act("delegate", {"task": "again"}),
            "Final Answer: done",
        ]
    )
    events: list[dict] = []
    r = asyncio.run(
        Agent(cfg, tmp_path, ApprovalPolicy("auto"), on_event=events.append).run("main task")
    )
    assert r.answer == "done"
    assert len(scripted.calls) == 5
    sub_msgs = scripted.calls[1].messages
    assert len(sub_msgs) == 2
    assert sub_msgs[1].content == "Task: list the files and summarize"
    assert "sub-agent" in sub_msgs[0].content
    assert "Sub-agent summary:\nSUBSUMMARY two files" in scripted.calls[3].messages[-1].content
    for idx in (0, 3, 4):
        assert all("zzz_marker" not in m.content for m in scripted.calls[idx].messages)
    assert "delegation limit reached (1 per session)" in scripted.calls[4].messages[-1].content
    assert r.summary["delegated"]["calls"] == 2
    assert r.session.delegations == 1
    delegate_events = [e for e in events if e["type"] in ("delegate_start", "delegate_end")]
    assert [e["type"] for e in delegate_events] == ["delegate_start", "delegate_end"]
    assert delegate_events[1]["ok"] is True


def test_subagent_cannot_redelegate(tmp_path, mock_config, scripted):
    cfg = deleg(mock_config)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            act("delegate", {"task": "nested"}),
            "Final Answer: s",
            "Final Answer: m",
        ]
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    assert "unknown tool 'delegate'" in scripted.calls[2].messages[-1].content
    assert r.answer == "m"


def test_subagent_max_steps_fallback(tmp_path, mock_config, scripted):
    cfg = deleg(mock_config, max_steps=2)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            act("list_files", {}),
            act("list_files", {}),
            "Final Answer: fallback ok",
        ]
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    assert "delegation failed (max_steps)" in scripted.calls[3].messages[-1].content
    assert r.answer == "fallback ok"
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_fallback_on_error(tmp_path, mock_config, scripted):
    cfg = deleg(mock_config)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            boom,
            act("delegate", {"task": "t2"}),
            "Final Answer: did it myself",
        ]
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    failed_msg = scripted.calls[2].messages[-1].content
    unavailable_msg = scripted.calls[3].messages[-1].content
    assert "delegation failed (error: ProviderError: boom)" in failed_msg
    assert "delegation is unavailable for the rest of this request" in unavailable_msg
    assert r.answer == "did it myself"
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_fallback_on_timeout(tmp_path, mock_config, scripted):
    cfg = deleg(mock_config, timeout_s=0.05)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            act("slow", {}),
            "Final Answer: main did it",
        ]
    )
    tools = [*default_tools(), SlowTool()]
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto"), tools=tools).run("main task"))
    assert "delegation failed (timeout)" in scripted.calls[2].messages[-1].content
    assert r.answer == "main did it"


def test_fallback_on_token_budget(tmp_path, mock_config, scripted):
    cfg = deleg(mock_config, max_tokens=10)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            "Final Answer: sub",
            "Final Answer: main",
        ]
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    assert "delegation failed (token_budget)" in scripted.calls[2].messages[-1].content
    assert r.answer == "main"


def test_cli_delegate_flag_fallback_exit0(scripted, ws, cfg_file):
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            boom,
            "Final Answer: fallback done",
        ]
    )
    result = CliRunner().invoke(
        app,
        [
            "run",
            "hello",
            "-w",
            str(ws),
            "-c",
            str(cfg_file),
            "--approval",
            "auto",
            "--delegate",
        ],
    )
    assert result.exit_code == 0
    assert "fallback done" in result.stdout
    assert len(scripted.calls) == 3


def test_delegation_disabled_is_m1(scripted, mock_config, tmp_path):
    scripted.script.extend([act("delegate", {"task": "t"}), "Final Answer: ok"])
    r = asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("main task"))
    assert "delegate" not in scripted.calls[0].messages[0].content
    assert "unknown tool 'delegate'" in scripted.calls[1].messages[-1].content
    assert r.summary["delegated"]["calls"] == 0


def test_subagent_same_approval_policy(tmp_path, mock_config, scripted):
    write_files(tmp_path, {"a.txt": "hello\n"})
    cfg = deleg(mock_config)
    asked: list[str] = []
    policy = ApprovalPolicy("ask", review=lambda req: (asked.append(req.tool), "no")[1])
    scripted.script.extend(
        [
            act("delegate", {"task": "edit"}),
            act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
            "Final Answer: s",
            "Final Answer: m",
        ]
    )
    asyncio.run(Agent(cfg, tmp_path, policy).run("main task"))
    assert asked == ["edit_file"]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert "denied by user" in scripted.calls[2].messages[-1].content

    scripted.script.extend(
        [
            act("delegate", {"task": "shell"}),
            act("run_shell", {"command": "echo hi > b.txt"}),
            "Final Answer: s",
            "Final Answer: m",
        ]
    )
    asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("deny")).run("main task"))
    assert not (tmp_path / "b.txt").exists()
    assert "denied by user" in scripted.calls[-2].messages[-1].content


def test_cost_cap_with_delegation(tmp_path, scripted):
    cfg = parse_config(tomllib.loads(FIXED_CFG_TOML))
    cfg = with_agent(cfg, max_cost_usd=0.0015, approval="auto")
    cfg = deleg(cfg)
    scripted.script.extend(
        [
            act("delegate", {"task": "t"}),
            act("list_files", {}),
            "Final Answer: never",
        ]
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("main task"))
    assert r.stop_reason == StopReason.COST_LIMIT
    assert r.answer is None
    assert len(scripted.calls) == 2
