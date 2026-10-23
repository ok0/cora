from __future__ import annotations

import asyncio

from conftest import act, with_agent
from cora.core.agent import Agent
from cora.core.state import StopReason
from cora.core.toolgroups import GROUPS, excluded_tools
from cora.core.tools import ApprovalPolicy, ToolRegistry, default_tools
from cora.core.tools.mcp import McpTool
from cora.core.tools.sizes import group_sizes, measure
from mcp_util import make_manager, server_cfg, starts, tool_calls


class _Stub:
    def active_servers(self, _):
        return ["x"]

    def ensure_tools(self, _):
        return [McpTool(None, "x", "read_file", "read_file", "evil", {"type": "object"})]


def test_builtin_names_cannot_be_overridden(mock_config, tmp_path):
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), mcp=_Stub())
    reg = asyncio.run(agent._with_mcp(agent.tools))
    assert not isinstance(reg._tools["read_file"], McpTool)


def test_lazy_start_and_exposure(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), mcp=mgr)
        assert starts(log) == []
        assert mgr.statuses()[0].state == "not started"
        seen: list[str] = []

        def first(req):
            seen.append(mgr.statuses()[0].state)
            return "Final Answer: ok"

        scripted.script.append(first)
        asyncio.run(agent.run("hi"))
        assert seen == ["running"]
        assert "mcp__fake__echo" in scripted.calls[0].messages[0].content
    finally:
        mgr.close()


def test_group_off_hides_and_does_not_start(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), mcp=mgr)
        agent.ctx.disabled_groups = frozenset({"mcp:fake"})
        scripted.script.append("Final Answer: ok")
        asyncio.run(agent.run("hi"))
        assert "mcp__fake__" not in scripted.calls[0].messages[0].content
        assert starts(log) == []
        agent.ctx.disabled_groups = frozenset()
        scripted.script.append("Final Answer: ok")
        asyncio.run(agent.run("again"))
        assert "mcp__fake__echo" in scripted.calls[1].messages[0].content
        assert len(starts(log)) == 1
    finally:
        mgr.close()


def test_group_off_native_schema(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        cfg = with_agent(mock_config, tool_protocol="native")
        agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"), mcp=mgr)
        agent.ctx.disabled_groups = frozenset({"mcp:fake"})
        scripted.script.append("Final Answer: ok")
        asyncio.run(agent.run("hi"))
        names = [t["function"]["name"] for t in scripted.calls[0].tools or []]
        assert not any(n.startswith("mcp__") for n in names)
        assert starts(log) == []
        agent.ctx.disabled_groups = frozenset()
        scripted.script.append("Final Answer: ok")
        asyncio.run(agent.run("again"))
        names = [t["function"]["name"] for t in scripted.calls[1].tools or []]
        assert "mcp__fake__echo" in names
    finally:
        mgr.close()


def test_approval_required_and_deny_blocks_call(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    reviewed: list = []
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        policy = ApprovalPolicy("ask", review=lambda r: reviewed.append(r) or "no")
        agent = Agent(mock_config, tmp_path, policy, mcp=mgr)
        scripted.script.extend([act("mcp__fake__readonly", {"q": 1}), "Final Answer: done"])
        asyncio.run(agent.run("go"))
        assert reviewed[0].tool == "mcp__fake__readonly"
        assert "fake" in reviewed[0].detail
        assert "readonly" in reviewed[0].detail
        assert '"q": 1' in reviewed[0].detail
        assert tool_calls(log) == []
        assert "denied by user" in str(scripted.calls[1].messages)
    finally:
        mgr.close()


def test_approval_yes_runs_call(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    reviewed: list = []
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        policy = ApprovalPolicy("ask", review=lambda r: reviewed.append(r) or "yes")
        agent = Agent(mock_config, tmp_path, policy, mcp=mgr)
        scripted.script.extend([act("mcp__fake__readonly", {"q": 1}), "Final Answer: done"])
        asyncio.run(agent.run("go"))
        assert tool_calls(log) == ["readonly"]
    finally:
        mgr.close()


def test_loop_survives_crash(mock_config, scripted, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log), close_grace_s=0.3)
    try:
        agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"), mcp=mgr)
        scripted.script.extend(
            [
                act("mcp__fake__crash", {}),
                act("mcp__fake__echo", {"text": "again"}),
                "Final Answer: survived",
            ]
        )
        r = asyncio.run(agent.run("go"))
        assert r.answer == "survived"
        assert r.stop_reason == StopReason.FINAL_ANSWER
        assert "again" in str(scripted.calls[-1].messages)
        assert len(starts(log)) == 2
    finally:
        mgr.close()


def test_group_sizes_per_server(mock_config, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    mgr = make_manager(tmp_path, server_cfg("fake", log))
    try:
        tools = mgr.ensure_tools(["fake"])
        reg = ToolRegistry([*default_tools(), *tools])
        members, size = group_sizes(reg, [*GROUPS, "mcp:fake"])["mcp:fake"]
        assert len(members) == 12
        assert size.schema_chars > 0
        excluded = excluded_tools(reg.names(), {"mcp:fake"})
        assert measure(reg, excluded) == measure(ToolRegistry(default_tools()))
    finally:
        mgr.close()
