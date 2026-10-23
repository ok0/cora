from __future__ import annotations

import asyncio
import json

import httpx

from conftest import with_agent
from cora.core.agent import Agent
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, Workspace, default_tools
from cora.core.tools.plan import SubmitPlanTool
from cora.core.types import CompletionResponse

NEW = {
    "todo_write": (True, False),
    "git_status": (True, False),
    "git_diff": (True, False),
    "git_log": (True, False),
    "git_add": (False, True),
    "git_commit": (False, True),
    "git_branch": (False, True),
    "web_fetch": (False, True),
    "submit_plan": (False, False),
}
NEW_TOOLS_DESCRIBE_BUDGET = 1300
NEW_TOOLS_SCHEMA_BUDGET = 3800
MAX_DESCRIPTION_CHARS = 120


def _new_tools():
    return [t for t in [*default_tools(), SubmitPlanTool()] if t.name in NEW]


def test_classification_table():
    found = set()
    for tool in [*default_tools(), SubmitPlanTool()]:
        if tool.name not in NEW:
            continue
        found.add(tool.name)
        assert (tool.read_only, tool.requires_approval) == NEW[tool.name], tool.name
        assert isinstance(tool.parameters, dict)
        assert tool.parameters["type"] == "object"
        assert callable(tool.preflight)
        if tool.requires_approval:
            assert callable(tool.preview), tool.name
    assert found == set(NEW)


def test_exposed_in_both_protocols(mock_config, scripted, tmp_path):
    names = [n for n in NEW if n != "submit_plan"]

    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run("hi"))
    system = scripted.calls[0].messages[0].content
    for name in names:
        assert name in system, name

    cfg = with_agent(mock_config, tool_protocol="native")
    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    scripted.script[:] = [CompletionResponse("done", 10, 5, "mock/cheap")]
    asyncio.run(agent.run("hi"))
    exposed = {t["function"]["name"] for t in scripted.calls[-1].tools}
    assert set(names) <= exposed

    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(agent.run("plan"))
    assert "- submit_plan:" in scripted.calls[-1].messages[0].content

    agent = Agent(cfg, tmp_path, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    scripted.script[:] = [CompletionResponse("done", 10, 5, "mock/cheap")]
    asyncio.run(agent.run("plan"))
    exposed = {t["function"]["name"] for t in scripted.calls[-1].tools}
    assert "submit_plan" in exposed


def test_no_web_search_tool():
    assert {"web_search", "search_web", "google", "bing"} & set(
        ToolRegistry(default_tools()).names()
    ) == set()


def test_description_budget():
    new_tools = _new_tools()
    describe_total = sum(
        len(f"- {t.name}: {t.description} Args: {t.args_doc}") for t in new_tools
    )
    assert describe_total <= NEW_TOOLS_DESCRIBE_BUDGET
    schema_total = sum(len(json.dumps(s)) for s in ToolRegistry(new_tools).schemas())
    assert schema_total <= NEW_TOOLS_SCHEMA_BUDGET
    for t in new_tools:
        assert len(t.description) <= MAX_DESCRIPTION_CHARS, t.name


async def _forbidden_resolver(host: str, port: int) -> list[str]:
    raise AssertionError("real DNS used")


def test_plan_mode_table_all_tools(tmp_path):
    transport_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        transport_calls.append(request)
        return httpx.Response(200, text="unexpected")

    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    reg = ToolRegistry(default_tools())
    ctx = ToolContext(
        Workspace(tmp_path),
        ApprovalPolicy("auto"),
        plan_mode=True,
        http_transport=httpx.MockTransport(handler),
        resolver=_forbidden_resolver,
    )
    denied = [
        ("edit_file", {"path": "a.txt", "old": "", "new": "x"}),
        ("run_shell", {"command": "touch x"}),
        ("git_add", {"paths": ["a.txt"]}),
        ("git_commit", {"message": "m"}),
        ("git_branch", {"name": "b", "create": True}),
        ("web_fetch", {"url": "https://example.com/"}),
    ]
    allowed = [
        ("list_files", {}),
        ("read_file", {"path": "a.txt"}),
        ("search", {"pattern": "x"}),
        ("todo_write", {"todos": []}),
        ("git_status", {}),
        ("git_diff", {}),
        ("git_log", {}),
    ]
    for name, args in denied:
        res = asyncio.run(reg.execute(name, args, ctx))
        assert "plan mode is on" in res.output, name
    for name, args in allowed:
        res = asyncio.run(reg.execute(name, args, ctx))
        assert "plan mode is on" not in res.output, name
    assert transport_calls == []
    assert not (tmp_path / "x").exists()
