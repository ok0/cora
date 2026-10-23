from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from conftest import with_gates_off
from cora.core.agent import Agent
from cora.core.react import INPUT_ERROR, parse_turn, truncated_error
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionResponse

FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))
OLD_MSG = (
    "edit_file failed: 'old' text not found in md2html.py. It must match the file exactly, "
    "including whitespace and indentation. Re-read the file with read_file and copy the exact "
    "lines without the line-number prefix."
)
TASK = "make the program"


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


@pytest.mark.parametrize("lenient", [False, True])
def test_pin_write_escape_parse(lenient):
    t = parse_turn(FIX["write_escape"]["reply"], lenient=lenient, first_arg=FA, json_strings=True)
    assert t.error == "Action Input must be a single JSON object"
    assert t.calls == ()


def test_pin_write_escape_observation(mock_config, scripted, ws):
    cfg = with_gates_off(mock_config, approval="auto", json_string_repair=True)
    scripted.script[:] = [FIX["write_escape"]["reply"], "Final Answer: done"]
    r = run(cfg, ws)
    assert scripted.calls[1].messages[-1].content == "Observation: " + INPUT_ERROR
    assert events(r, "parse_error")[0]["error"] == INPUT_ERROR
    assert all(c.temperature == 0.0 for c in scripted.calls)
    assert events(r, "repeat_detected") == []


def test_pin_edit_backslash_old_not_found(mock_config, scripted, ws):
    before = FIX["edit_backslash"]["file"]
    (ws / "md2html.py").write_text(before, encoding="utf-8")
    cfg = with_gates_off(mock_config, approval="auto", json_string_repair=True)
    scripted.script[:] = [FIX["edit_backslash"]["reply"], "Final Answer: done"]
    r = run(cfg, ws)
    assert scripted.calls[1].messages[-1].content == "Observation: " + OLD_MSG
    assert (ws / "md2html.py").read_bytes() == before.encode("utf-8")
    assert any(e["ok"] is False for e in events(r, "tool_call"))


def test_pin_truncated_edit(mock_config, scripted, ws):
    reply = FIX["truncated_edit"]["reply"]
    assert parse_turn(reply, lenient=True, first_arg=FA, json_strings=True).error == INPUT_ERROR
    cfg = with_gates_off(mock_config, approval="auto", json_string_repair=True)
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    r = run(cfg, ws)
    assert scripted.calls[1].messages[-1].content == "Observation: " + truncated_error(4096)
    assert len(events(r, "reply_truncated")) == 1


def test_m17b_fixture_sanitized():
    raw = (Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8")
    patterns = [
        r"sk-or-",
        r"sk-[A-Za-z0-9]{16}",
        r"AIza",
        r"(?i)authorization",
        r"(?i)bearer ",
        r"OPENROUTER_API_KEY=",
        r"GEMINI_API_KEY=",
        r"/private/var/",
        r"/var/folders/",
        r"/Users/",
        re.escape(str(Path.home())),
    ]
    for pat in patterns:
        assert re.search(pat, raw) is None, pat
    for name in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(name, "")
        if len(value) >= 8:
            assert value not in raw, name
    assert {"write_escape", "edit_backslash", "truncated_edit"} <= set(FIX)
