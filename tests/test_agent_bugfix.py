from __future__ import annotations

import asyncio

from conftest import PY, act, write_files
from cora.bench.tasks import BENCH_TASKS
from cora.core.agent import Agent
from cora.core.observability import read_events
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy


def test_agent_reads_edits_and_tests_to_fix_bug(scripted, mock_config, tmp_path):
    write_files(tmp_path, BENCH_TASKS[0].files)
    check = f"{PY} -m pytest -q -p no:cacheprovider"
    scripted.script[:] = [
        act("read_file", {"path": "calc.py"}),
        act("edit_file", {"path": "calc.py", "old": "return a - b", "new": "return a + b"}),
        act("run_shell", {"command": check}),
        "Thought: done\nFinal Answer: fixed add",
    ]
    r = asyncio.run(
        Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run(
            BENCH_TASKS[0].prompt, check_command=check
        )
    )
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert "a + b" in (tmp_path / "calc.py").read_text(encoding="utf-8")

    events = read_events(r.log_path)
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert [e["tool"] for e in tool_calls] == ["read_file", "edit_file", "run_shell"]
    shell_event = tool_calls[2]
    assert shell_event["ok"] is True
    assert "passed" in shell_event["output_head"]
    check_events = [e for e in events if e["type"] == "check"]
    assert check_events[-1]["ok"] is True
