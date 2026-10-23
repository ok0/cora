from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from conftest import PY, act, with_agent, write_files
from cora.bench.tasks import BENCH_TASKS
from cora.core.agent import Agent
from cora.core.errors import InvalidTransition
from cora.core.observability import read_events
from cora.core.state import AgentState, Session, SessionStore, StopReason
from cora.core.tools import ApprovalPolicy


def test_invalid_transition_raises():
    s = Session(id="s", task="t")
    with pytest.raises(InvalidTransition):
        s.transition(AgentState.DONE)


def test_resume_continues_from_saved_state(scripted, mock_config, tmp_path):
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")

    def crash(req):
        raise RuntimeError("simulated crash")

    scripted.script[:] = [act("list_files", {}), act("read_file", {"path": "a.txt"}), crash]
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    with pytest.raises(RuntimeError):
        asyncio.run(agent.run("inspect a.txt"))

    store = SessionStore(tmp_path / ".cora" / "sessions")
    sid = store.list_ids()[0]
    saved = store.load(sid)
    assert saved.iteration == 2
    assert saved.state == AgentState.THINKING

    scripted.calls.clear()
    scripted.script[:] = ["Final Answer: resumed-ok"]
    resumed = asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).resume(sid))
    assert resumed.answer == "resumed-ok"
    assert resumed.session.total_iterations == 3
    assert any(m.content.startswith("Observation:") for m in scripted.calls[0].messages)
    assert any(e["type"] == "resumed" for e in read_events(resumed.log_path))


def test_resume_done_session_is_noop(scripted, mock_config, tmp_path):
    scripted.script[:] = ["Final Answer: finished"]
    agent = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    first = asyncio.run(agent.run("say it"))
    calls_before = len(scripted.calls)
    resumer = Agent(mock_config, tmp_path, ApprovalPolicy("auto"))
    second = asyncio.run(resumer.resume(first.session.id))
    assert len(scripted.calls) == calls_before
    assert second.answer == first.answer


def test_src_never_references_reference_dir():
    src = Path(__file__).resolve().parents[1] / "src"
    allowed = src / "cora" / "core" / "tools" / "base.py"
    hits = []
    for path in src.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ".reference" in line:
                hits.append((path, lineno, line.strip()))
    assert hits == [(allowed, hits[0][1] if hits else 0, '".reference",')], hits


def test_resume_from_reflecting_uses_persisted_failure(scripted, mock_config, tmp_path):
    cfg = with_agent(mock_config, max_attempts=2)
    write_files(tmp_path, BENCH_TASKS[0].files)
    check = f"{PY} -B -m pytest -q -p no:cacheprovider"

    def crash(req):
        raise RuntimeError("simulated crash during reflection")

    scripted.script[:] = ["Final Answer: done", crash]
    with pytest.raises(RuntimeError):
        asyncio.run(
            Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("fix add", check_command=check)
        )

    store = SessionStore(tmp_path / ".cora" / "sessions")
    sid = store.list_ids()[0]
    saved = store.load(sid)
    assert saved.state == AgentState.REFLECTING
    assert saved.last_failure and "1 failed" in saved.last_failure

    scripted.calls.clear()
    scripted.script[:] = [
        "Reflection: change 'a - b' to 'a + b' in calc.py.",
        act("edit_file", {"path": "calc.py", "old": "return a - b", "new": "return a + b"}),
        "Final Answer: fixed",
    ]
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).resume(sid))
    assert "1 failed" in scripted.calls[0].messages[0].content
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.session.attempt == 1
    assert r.session.last_failure is None
