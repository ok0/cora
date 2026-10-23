from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from conftest import with_gates_off
from cora.core.agent import Agent
from cora.core.react import ESCAPE_HINT, INPUT_ERROR, RAW_HINT, parse_turn
from cora.core.tools import ApprovalPolicy
from cora.core.tools.base import ToolContext, Workspace
from cora.core.tools.builtin import EditFileTool, _write_finding

FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))
TASK = "make the program"
OLD_MSG = (
    "edit_file failed: 'old' text not found in md2html.py. It must match the file exactly, "
    "including whitespace and indentation. Re-read the file with read_file and copy the exact "
    "lines without the line-number prefix."
)


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def located_cfg(mock_config):
    return with_gates_off(
        mock_config, approval="auto", json_string_repair=True, located_errors=True
    )


def first_diff(old_lines: list[str], file_lines: list[str]) -> tuple[int, int]:
    for i, a in enumerate(old_lines):
        b = file_lines[i]
        if a != b:
            n = 0
            while n < min(len(a), len(b)) and a[n] == b[n]:
                n += 1
            return i + 1, n + 1
    raise AssertionError("no difference")


def test_located_input_error_fixture():
    e = parse_turn(
        FIX["write_escape"]["reply"], lenient=True, first_arg=FA, json_strings=True, located=True
    ).error
    assert e.startswith(
        INPUT_ERROR + ": Expecting ',' delimiter at character 636 of the JSON object."
    )
    m = re.search(r"\(» marks it\): (.*)", e)
    assert m is not None
    assert len(m.group(1).replace("»", "")) <= 60
    assert "href=" in m.group(1)
    assert ESCAPE_HINT in e
    assert "<<<" not in e


def test_located_raw_hint():
    e = parse_turn(
        FIX["write_escape"]["reply"],
        lenient=True,
        first_arg=FA,
        json_strings=True,
        raw_blocks=True,
        located=True,
    ).error
    assert RAW_HINT in e


def test_located_off_identical():
    kw = {"lenient": True, "first_arg": FA, "json_strings": True}
    reply = FIX["write_escape"]["reply"]
    assert parse_turn(reply, located=False, **kw).error == INPUT_ERROR
    assert parse_turn(reply, raw_blocks=True, located=False, **kw).error == INPUT_ERROR


def test_located_no_brace():
    e = parse_turn(
        "Thought: t\nAction: read_file\nAction Input: path", located=True
    ).error
    assert "no JSON object follows" in e


def test_located_agent_event(mock_config, scripted, ws):
    scripted.script[:] = [FIX["write_escape"]["reply"], "Final Answer: done"]
    r = run(located_cfg(mock_config), ws)
    assert "character 636" in events(r, "parse_error")[0]["error"]


def test_located_edit_backslash(mock_config, scripted, ws):
    file = FIX["edit_backslash"]["file"]
    reply = FIX["edit_backslash"]["reply"]
    (ws / "md2html.py").write_text(file, encoding="utf-8")
    old = parse_turn(reply, lenient=True, first_arg=FA, json_strings=True).calls[0].args["old"]
    k, c = first_diff(old.split("\n"), file.split("\n"))
    scripted.script[:] = [reply, "Final Answer: done"]
    run(located_cfg(mock_config), ws)
    out = scripted.calls[1].messages[-1].content
    assert out.startswith("Observation: " + OLD_MSG)
    assert f"line {k}, column {c}" in out
    assert "closest to line 1 of md2html.py" in out
    assert len(re.findall(r"^\s*\d+\| ", out, re.M)) <= 3
    assert len(out) < 1500
    assert file[-200:] not in out


def test_located_edit_no_similar(tmp_path):
    (tmp_path / "f.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"), located_errors=True)
    res = asyncio.run(EditFileTool().run({"path": "f.txt", "old": "zzzz qqqq", "new": "x"}, ctx))
    assert "No line in f.txt is similar" in res.output


def test_located_edit_off_identical(tmp_path):
    (tmp_path / "f.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"), located_errors=False)
    res = asyncio.run(EditFileTool().run({"path": "f.txt", "old": "zzzz qqqq", "new": "x"}, ctx))
    assert res.output == OLD_MSG.replace("md2html.py", "f.txt")


def test_located_protected_no_excerpt(tmp_path):
    (tmp_path / "credentials.json").write_text("SECRET-VALUE-123\n", encoding="utf-8")
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"), located_errors=True)
    assert _write_finding(ctx, tmp_path / "credentials.json") is not None
    res = asyncio.run(
        EditFileTool().run(
            {"path": "credentials.json", "old": "SECRET-VALUE-12X", "new": "x"}, ctx
        )
    )
    assert "SECRET-VALUE" not in res.output
