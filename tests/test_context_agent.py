from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

from conftest import act
from cora.core.agent import Agent
from cora.core.config import ContextSettings, DelegationSettings, MemorySettings
from cora.core.repomap import RepoMap
from cora.core.tools import ApprovalPolicy
from cora.core.types import messages_tokens
from repo_fixture import PLANTED, SECRET, make_large_repo

SUPERSEDED_A = "[superseded: a.txt read again later]"


def cfg_for(mock_config: Any, **ctx: Any) -> Any:
    return dataclasses.replace(
        mock_config,
        context=ContextSettings(**ctx),
        memory=MemorySettings(
            context_budget_tokens=100_000, keep_last_messages=8, max_observation_chars=4000
        ),
    )


def total(calls: list) -> int:
    return sum(messages_tokens(c.messages) for c in calls)


def policy(req: Any) -> Any:
    sysm = req.messages[0].content
    has_map = "Repository map" in sysm and "answer.py" in sysm
    steps = ([] if has_map else [act("list_files", {})]) + [
        act("read_file", {"path": "pkg/big_a.py"}),
        act("read_file", {"path": "answer.py"}),
        act("read_file", {"path": "pkg/big_a.py"}),
        "Thought: done\nFinal Answer: the answer is 42",
    ]
    n = sum(1 for m in req.messages if m.role == "assistant")
    return steps[n]


def run_arm(tmp_path: Path, scripted: Any, mock_config: Any, name: str, **ctx: Any) -> tuple:
    ws = make_large_repo(tmp_path / name)
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend([policy] * 10)
    r = asyncio.run(
        Agent(
            cfg_for(mock_config, repo_map_max_chars=1500, **ctx), ws, ApprovalPolicy("auto")
        ).run("find the answer")
    )
    return r, total(scripted.calls), list(scripted.calls)


def run_steps(ws: Path, scripted: Any, cfg: Any, steps: list, task: str = "task") -> tuple:
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend(steps)
    r = asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))
    return r, list(scripted.calls)


def small_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.txt").write_text("".join(f"line {i}\n" for i in range(50)), encoding="utf-8")
    return ws


def test_tokens_on_lower_than_off(tmp_path, scripted, mock_config, no_network):
    off, off_tok, _ = run_arm(tmp_path, scripted, mock_config, "off")
    both, both_tok, _ = run_arm(
        tmp_path, scripted, mock_config, "both", repo_map=True, dedupe_reads=True
    )
    mp, map_tok, _ = run_arm(tmp_path, scripted, mock_config, "map", repo_map=True)
    dd, dd_tok, _ = run_arm(tmp_path, scripted, mock_config, "dedupe", dedupe_reads=True)
    assert off.answer == both.answer == mp.answer == dd.answer == "the answer is 42"
    assert both_tok < off_tok
    assert map_tok < off_tok
    assert dd_tok < off_tok
    assert no_network == []


def test_on_run_prompt_has_no_secret(tmp_path, scripted, mock_config):
    _, _, calls = run_arm(
        tmp_path, scripted, mock_config, "secret", repo_map=True, dedupe_reads=True
    )
    sysm = calls[0].messages[0].content
    assert SECRET not in sysm
    assert "Repository map" in sysm
    lines = sysm.split("\n")
    assert not any(line.startswith(p + " (") for p in PLANTED for line in lines)


def test_defaults_equal_pre_m5(tmp_path, scripted, mock_config):
    ws = small_ws(tmp_path)
    steps = [act("read_file", {"path": "a.txt"}), act("read_file", {"path": "a.txt"}),
             "Final Answer: ok"]
    r, calls = run_steps(ws, scripted, mock_config, steps)
    _, calls2 = run_steps(
        ws, scripted, dataclasses.replace(mock_config, context=ContextSettings()), steps
    )
    assert calls[0].messages[0].content == calls2[0].messages[0].content
    assert "Repository map" not in calls[0].messages[0].content
    last = calls[-1].messages
    observations = [
        m.content for m in last if m.role == "user" and m.content.startswith("Observation: ")
    ]
    assert len(observations) == 2
    assert all("line 0" in o for o in observations)
    assert not any("[superseded" in m.content for m in last)
    assert "read_paths" not in r.session.memory
    assert not (ws / ".cora" / "index").exists()


def test_dedupe_marker_in_run(tmp_path, scripted, mock_config):
    ws = small_ws(tmp_path)
    steps = [act("read_file", {"path": "a.txt"}), act("read_file", {"path": "a.txt"}),
             "Final Answer: ok"]
    _, calls = run_steps(ws, scripted, cfg_for(mock_config, dedupe_reads=True), steps)
    last = calls[-1].messages
    assert [m.content for m in last].count(SUPERSEDED_A) == 1
    latest = [m.content for m in last if m.role == "user" and m.content.startswith("Observation: ")]
    assert latest and "line 0" in latest[-1]


def test_resumed_session_keeps_behavior(tmp_path, scripted, mock_config):
    ws = small_ws(tmp_path)
    cfg = cfg_for(mock_config, repo_map=True, dedupe_reads=True)
    scripted.script.clear()
    scripted.calls.clear()
    scripted.script.extend([act("read_file", {"path": "a.txt"}), "Final Answer: one"])
    agent1 = Agent(cfg, ws, ApprovalPolicy("auto"))
    r1 = asyncio.run(agent1.run("first"))
    agent2 = Agent(cfg, ws, ApprovalPolicy("auto"))
    s = agent2.sessions.load(r1.session.id)
    scripted.calls.clear()
    scripted.script.extend([act("read_file", {"path": "a.txt"}), "Final Answer: two"])
    asyncio.run(agent2.run("again", session=s))
    last = scripted.calls[-1].messages
    assert last[0].role == "system" and "Repository map" in last[0].content
    assert [m.content for m in last].count(SUPERSEDED_A) == 1
    latest = [m.content for m in last if m.role == "user" and m.content.startswith("Observation: ")]
    assert latest and "line 0" in latest[-1]


def test_subagent_gets_map_and_dedupe(tmp_path, scripted, mock_config, no_network):
    ws = small_ws(tmp_path)
    cfg = dataclasses.replace(
        cfg_for(mock_config, repo_map=True, dedupe_reads=True),
        delegation=DelegationSettings(enabled=True),
    )
    steps = [
        act("delegate", {"task": "inspect a"}),
        act("read_file", {"path": "a.txt"}),
        act("read_file", {"path": "./a.txt"}),
        "Final Answer: SUB",
        "Final Answer: done",
    ]
    r, calls = run_steps(ws, scripted, cfg, steps)
    assert r.answer == "done"
    assert "Repository map" in calls[1].messages[0].content
    sub_last = calls[3].messages
    assert SUPERSEDED_A in [m.content for m in sub_last]
    obs = [m.content for m in sub_last if m.content.startswith("Observation:")]
    assert len(obs) == 1 and "line 0" in obs[0]
    assert no_network == []


def test_repo_map_built_once_per_run(tmp_path, scripted, mock_config, monkeypatch):
    ws = small_ws(tmp_path)
    original = RepoMap.build
    counter = {"n": 0}

    def counting(*args: Any, **kwargs: Any) -> RepoMap:
        counter["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(RepoMap, "build", counting)
    steps = [act("list_files", {}), act("read_file", {"path": "a.txt"}), "Final Answer: ok"]
    run_steps(ws, scripted, cfg_for(mock_config, repo_map=True), steps)
    assert counter["n"] == 1
