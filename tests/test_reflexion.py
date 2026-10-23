from __future__ import annotations

import asyncio

from conftest import PY, act, with_agent, write_files
from cora.bench.tasks import BENCH_TASKS
from cora.core.agent import Agent
from cora.core.observability import read_events
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy

CHECK = f"{PY} -B -m pytest -q -p no:cacheprovider"


def test_reflection_retry_uses_strong_model(scripted, mock_config, tmp_path):
    cfg = with_agent(mock_config, max_attempts=2)
    write_files(tmp_path, BENCH_TASKS[0].files)
    scripted.script[:] = [
        "Thought: guess\nFinal Answer: done",
        "Reflection: I never edited calc.py; change 'a - b' to 'a + b' before answering.",
        act("edit_file", {"path": "calc.py", "old": "return a - b", "new": "return a + b"}),
        "Final Answer: fixed",
    ]
    r = asyncio.run(
        Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("fix add", check_command=CHECK)
    )
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.session.attempt == 1

    events = read_events(r.log_path)
    reflections = [e for e in events if e["type"] == "reflection"]
    assert "never edited calc.py" in reflections[0]["text"]

    attempt_starts = [e for e in events if e["type"] == "attempt_start"]
    assert attempt_starts[1]["attempt"] == 1
    assert "never edited calc.py" in attempt_starts[1]["system_prompt"]

    assert "never edited calc.py" in scripted.calls[2].messages[0].content

    routes = [e for e in events if e["type"] == "route"]
    assert routes[1]["tier"] == "strong"
    assert "forced:strong" in routes[1]["reasons"]


def test_no_retry_beyond_max_attempts(scripted, mock_config, tmp_path):
    cfg = with_agent(mock_config, max_attempts=1)
    write_files(tmp_path, BENCH_TASKS[0].files)
    scripted.script[:] = ["Final Answer: done"]
    r = asyncio.run(
        Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("fix add", check_command=CHECK)
    )
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert not [e for e in read_events(r.log_path) if e["type"] == "reflection"]
