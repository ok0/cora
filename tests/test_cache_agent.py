from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

import httpx

from conftest import ScriptedProvider, act, native, tc, with_agent
from cora.core.agent import Agent
from cora.core.config import CacheSettings, DelegationSettings, MemorySettings
from cora.core.metering import format_summary
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.tools import ApprovalPolicy
from cora.core.tools.builtin import default_tools
from cora.core.tools.registry import ToolRegistry
from cora.core.types import CompletionResponse, estimate_tokens, messages_tokens
from repo_fixture import SECRET, make_large_repo

COMPRESS = {"compress_observations": True, "compress_chars": 300}
ALL_ON = {**COMPRESS, "prompt_cache": True, "tool_descriptions": "terse"}
STEPS = [
    act("list_files", {}),
    act("search", {"pattern": "zzz_no_match_zzz"}),
    act("search", {"pattern": "def "}),
    act("read_file", {"path": "answer.py"}),
    "Thought: done\nFinal Answer: the answer is 42",
]
ANSWER = "the answer is 42"


def cfg(
    mock_config: Any,
    *,
    cache: Any = None,
    model_cache: bool = False,
    keep_last: int = 2,
    **agent: Any,
) -> Any:
    settings = cache if isinstance(cache, CacheSettings) else CacheSettings(**(cache or {}))
    config = dataclasses.replace(
        mock_config,
        cache=settings,
        memory=MemorySettings(100_000, keep_last, 4000),
        models=tuple(dataclasses.replace(m, cache=model_cache) for m in mock_config.models),
    )
    return with_agent(config, **agent) if agent else config


def run(scripted: Any, ws: Path, config: Any, steps: list, task: str = "find the answer") -> tuple:
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend(steps)
    r = asyncio.run(Agent(config, ws, ApprovalPolicy("auto")).run(task))
    return r, list(scripted.calls)


def repo(tmp_path: Path) -> Path:
    return make_large_repo(tmp_path / "repo", py_files=60, other_files=20)


def obs(messages: list) -> list[str]:
    return [
        m.content
        for m in messages
        if m.role == "tool" or (m.role == "user" and m.content.startswith("Observation:"))
    ]


def provider(monkeypatch: Any) -> OpenRouterProvider:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")
    return OpenRouterProvider(
        {}, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )


def test_defaults_equal_pre_m6(tmp_path, scripted, mock_config, no_network, monkeypatch):
    ws = repo(tmp_path)
    r1, c1 = run(scripted, ws, mock_config, list(STEPS))
    r2, c2 = run(
        scripted, ws, dataclasses.replace(mock_config, cache=CacheSettings()), list(STEPS)
    )
    assert [[(m.role, m.content) for m in c.messages] for c in c1] == [
        [(m.role, m.content) for m in c.messages] for c in c2
    ]
    for c in c1:
        assert c.cache_prefix is False
        assert all("[compressed:" not in m.content for m in c.messages)
    shell = next(t for t in default_tools() if t.name == "run_shell")
    assert shell.description in c1[0].messages[0].content
    assert "read_paths" not in r1.session.memory
    body = json.dumps(provider(monkeypatch)._body(c1[0]))
    assert "cache_control" not in body
    assert ANSWER == r1.answer == r2.answer
    assert no_network == []


def test_terse_lower_same_results(tmp_path, scripted, mock_config, no_network):
    ws = repo(tmp_path)
    full_r, full = run(scripted, ws, cfg(mock_config), list(STEPS))
    terse_r, terse = run(
        scripted, ws, cfg(mock_config, cache={"tool_descriptions": "terse"}), list(STEPS)
    )
    assert full_r.answer == terse_r.answer == ANSWER
    assert obs(full[-1].messages) == obs(terse[-1].messages)
    assert estimate_tokens(terse[0].messages[0].content) < estimate_tokens(
        full[0].messages[0].content
    )
    sysm = terse[0].messages[0].content
    assert "Run a shell command in the workspace." in sysm
    assert "working directory" not in sysm
    assert no_network == []


def test_terse_native(tmp_path, scripted, mock_config, no_network):
    ws = repo(tmp_path)
    script = [
        native(tc("read_file", {"path": "answer.py"})),
        CompletionResponse("done", 10, 5, "mock/cheap"),
    ]
    full_r, full = run(scripted, ws, cfg(mock_config, tool_protocol="native"), list(script))
    terse_r, terse = run(
        scripted,
        ws,
        cfg(mock_config, cache={"tool_descriptions": "terse"}, tool_protocol="native"),
        list(script),
    )
    assert full_r.answer == terse_r.answer == "done"
    assert all(len(t["function"]["description"]) <= 60 for t in terse[0].tools)

    def specs(calls: list) -> list:
        return [(t["function"]["name"], t["function"]["parameters"]) for t in calls[0].tools]

    assert specs(terse) == specs(full)
    assert no_network == []


def test_compression_lower_same_answer(tmp_path, scripted, mock_config, no_network):
    ws = repo(tmp_path)
    off_r, off = run(scripted, ws, cfg(mock_config), list(STEPS))
    on_r, on = run(scripted, ws, cfg(mock_config, cache=COMPRESS), list(STEPS))
    assert off_r.answer == on_r.answer == ANSWER
    assert sum(messages_tokens(c.messages) for c in on) < sum(
        messages_tokens(c.messages) for c in off
    )
    on_last, off_last = on[-1].messages, off[-1].messages
    on_obs, off_obs = obs(on_last), obs(off_last)
    assert len(on_obs) == len(off_obs) == 4
    assert "[compressed:" in on_obs[0]
    assert "[compressed:" in on_obs[2]
    assert on_obs[1] == off_obs[1]
    assert on_obs[3] == off_obs[3]
    assert on_last[0].content == off_last[0].content
    assert [m.content for m in on_last if m.content.startswith("Task: ")] == [
        m.content for m in off_last if m.content.startswith("Task: ")
    ]
    assert no_network == []


def test_prompt_cache_flag(tmp_path, scripted, mock_config, no_network, monkeypatch):
    ws = repo(tmp_path)
    _, on = run(scripted, ws, cfg(mock_config, cache={"prompt_cache": True}, model_cache=True),
                list(STEPS))
    assert all(c.cache_prefix is True for c in on)
    _, no_model = run(scripted, ws, cfg(mock_config, cache={"prompt_cache": True}), list(STEPS))
    assert all(c.cache_prefix is False for c in no_model)
    _, off = run(scripted, ws, cfg(mock_config, model_cache=True), list(STEPS))
    assert all(c.cache_prefix is False for c in off)
    p = provider(monkeypatch)
    body = p._body(on[0])
    assert body["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in json.dumps(m) for m in body["messages"][1:])
    off_req = off[0]
    assert json.dumps(p._body(off_req)) == json.dumps(
        p._body(dataclasses.replace(off_req, cache_prefix=False))
    )
    assert no_network == []


def test_cached_tokens_in_summary(tmp_path, scripted, mock_config, no_network, monkeypatch):
    ws = repo(tmp_path)
    original = ScriptedProvider.complete

    async def cached(self: Any, req: Any) -> CompletionResponse:
        resp = await original(self, req)
        return dataclasses.replace(resp, cached_input_tokens=5)

    monkeypatch.setattr(ScriptedProvider, "complete", cached)
    r, calls = run(scripted, ws, cfg(mock_config), list(STEPS))
    assert r.summary["by_model"]["mock/cheap"]["cached_input_tokens"] == 5 * len(calls)
    assert "cached=" in format_summary(r.summary)
    assert no_network == []


def test_combinations_same_answer(tmp_path, scripted, mock_config, no_network):
    ws = repo(tmp_path)
    combos = [
        ({"prompt_cache": True}, True),
        ({"tool_descriptions": "terse"}, False),
        (COMPRESS, False),
        (ALL_ON, True),
    ]
    for cache, model_cache in combos:
        r, _ = run(scripted, ws, cfg(mock_config, cache=cache, model_cache=model_cache),
                   list(STEPS))
        assert r.answer == ANSWER
    assert no_network == []


def test_resume_and_subagent_honor_settings(tmp_path, scripted, mock_config, no_network):
    ws = repo(tmp_path)
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend(list(STEPS))
    agent1 = Agent(cfg(mock_config, cache=COMPRESS), ws, ApprovalPolicy("auto"))
    r1 = asyncio.run(agent1.run("first"))
    agent2 = Agent(
        cfg(mock_config, cache={**COMPRESS, "prompt_cache": True}, model_cache=True),
        ws,
        ApprovalPolicy("auto"),
    )
    s = agent2.sessions.load(r1.session.id)
    scripted.calls.clear()
    scripted.script.extend(["Final Answer: two"])
    asyncio.run(agent2.run("second", session=s))
    first_call = scripted.calls[0]
    assert any("[compressed:" in m.content for m in first_call.messages)
    assert first_call.cache_prefix is True

    delegating = dataclasses.replace(
        cfg(mock_config, cache=ALL_ON, model_cache=True, keep_last=2),
        delegation=DelegationSettings(enabled=True),
    )
    steps = [
        act("delegate", {"task": "look", "mode": "general"}),
        act("list_files", {}),
        act("search", {"pattern": "def "}),
        "Thought: done\nFinal Answer: sub done",
        "Thought: done\nFinal Answer: the answer is 42",
    ]
    _, calls = run(scripted, ws, delegating, steps)
    subs = [c for c in calls if len(c.messages) > 1 and c.messages[1].content == "Task: look"]
    assert len(subs) == 3
    assert all(c.cache_prefix is True for c in subs)
    assert all("List files recursively." in c.messages[0].content for c in subs)
    assert any("[compressed:" in m.content for m in subs[2].messages)
    assert no_network == []


def test_no_secret_exposed(tmp_path, scripted, mock_config, no_network, monkeypatch):
    ws = repo(tmp_path)
    config = cfg(mock_config, cache=ALL_ON, model_cache=True)
    steps = [
        act("read_file", {"path": ".env"}),
        act("list_files", {}),
        act("search", {"pattern": "def "}),
        "Thought: done\nFinal Answer: the answer is 42",
    ]
    r, calls = run(scripted, ws, config, steps)
    p = provider(monkeypatch)
    assert any("denied: credential file: .env" in o for o in obs(calls[1].messages))
    for c in calls:
        text = "".join(m.content for m in c.messages)
        assert SECRET not in text
        body = json.dumps(p._body(c))
        assert SECRET not in body
        assert "k-test" not in body
    assert SECRET not in json.dumps(r.session.memory)
    assert SECRET not in ToolRegistry(default_tools()).describe(terse=True)
    assert no_network == []
