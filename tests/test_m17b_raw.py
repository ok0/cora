from __future__ import annotations

import asyncio
import json
from pathlib import Path

from conftest import with_gates_off
from cora.core.agent import Agent
from cora.core.react import RAW_UNCLOSED_ERROR, parse_turn, truncated_error
from cora.core.tools import ApprovalPolicy
from cora.core.tools.builtin import default_tools
from cora.core.tools.registry import ToolRegistry
from cora.core.types import CompletionResponse

FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))
TASK = "make the program"


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def write_block(path, content):
    return (
        f'Thought: write\nAction: write_file\nAction Input: {{"path": "{path}"}}\n'
        f"<<<CONTENT\n{content}\nCONTENT>>>"
    )


def edit_block(path, old, new):
    return (
        f'Thought: edit\nAction: edit_file\nAction Input: {{"path": "{path}"}}\n'
        f"<<<OLD\n{old}\nOLD>>>\n<<<NEW\n{new}\nNEW>>>"
    )


def cfg_on(mock_config, key: str):
    return with_gates_off(mock_config, approval="auto", json_string_repair=True, **{key: True})


def test_raw_write_verbatim_bytes(mock_config, scripted, ws):
    c = FIX["write_escape"]["intended_content"]
    t = parse_turn(write_block("md2html.py", c), raw_blocks=True)
    assert t.calls[0].args == {"path": "md2html.py", "content": c}
    assert t.repaired == ()
    scripted.script[:] = [write_block("md2html.py", c), "Final Answer: done"]
    r = run(cfg_on(mock_config, "raw_file_body"), ws)
    assert (ws / "md2html.py").read_bytes() == c.encode("utf-8")
    assert events(r, "parse_error") == []
    assert c.count('"') >= 30 and c.count("\\") >= 20


def test_raw_edit_backslash_succeeds(mock_config, scripted, ws):
    file = FIX["edit_backslash"]["file"]
    old = FIX["edit_backslash"]["intended_old"]
    new = FIX["edit_backslash"]["intended_new"]
    (ws / "md2html.py").write_text(file, encoding="utf-8")
    scripted.script[:] = [edit_block("md2html.py", old, new), "Final Answer: done"]
    r = run(cfg_on(mock_config, "raw_file_body"), ws)
    assert (ws / "md2html.py").read_text(encoding="utf-8") == file.replace(old, new, 1)
    assert any(e["ok"] is True and e.get("tool") == "edit_file" for e in events(r, "tool_call"))
    assert "\\[" in old


def test_raw_duplicate_field_named():
    a = (
        'Thought: write\nAction: write_file\nAction Input: {"path": "x.py", "content": "y"}\n'
        "<<<CONTENT\nz\nCONTENT>>>"
    )
    b = (
        'Thought: edit\nAction: edit_file\nAction Input: {"path": "x.py", "old": "a"}\n'
        "<<<OLD\nb\nOLD>>>\n<<<NEW\nc\nNEW>>>"
    )
    c = (
        'Thought: edit\nAction: edit_file\nAction Input: {"path": "x.py"}\n'
        "<<<OLD\na\nOLD>>>\n<<<OLD\nb\nOLD>>>\n<<<NEW\nc\nNEW>>>"
    )
    for reply, field in ((a, "content"), (b, "old"), (c, "old")):
        t = parse_turn(reply, raw_blocks=True)
        assert f"'{field}'" in t.error
        assert t.calls == ()


def test_raw_unclosed_block(mock_config, scripted, ws, tmp_path):
    reply = (
        'Thought: t\nAction: edit_file\nAction Input: {"path": "md2html.py"}\n<<<OLD\n'
        + FIX["edit_backslash"]["intended_old"][:3000]
    )
    unclosed = RAW_UNCLOSED_ERROR.format(open="<<<OLD", close="OLD>>>", seen="<<<OLD")
    assert unclosed.endswith("Marker-like lines in your reply: <<<OLD")
    assert parse_turn(reply, raw_blocks=True).error == unclosed
    cfg = cfg_on(mock_config, "raw_file_body")
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    r = run(cfg, ws)
    assert scripted.calls[1].messages[-1].content == "Observation: " + truncated_error(4096)
    assert len(events(r, "reply_truncated")) == 1
    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 100, req.model, finish_reason="stop"),
        "Final Answer: done",
    ]
    r2 = run(cfg, ws2)
    assert events(r2, "parse_error")[0]["error"] == unclosed


def test_raw_off_markers_plain_text():
    r = write_block("md2html.py", "a")
    kw = {"lenient": True, "first_arg": FA, "json_strings": True}
    off = parse_turn(r, **kw)
    assert parse_turn(r, raw_blocks=False, **kw) == off
    assert off.calls and "content" not in off.calls[0].args


def test_raw_other_tools_unchanged():
    for reply in (
        'Thought: t\nAction: run_shell\nAction Input: {"command": "echo"}\n'
        "<<<CONTENT\nx\nCONTENT>>>",
        'Thought: t\nAction: edit_file\nAction Input: {"path": "a"}\n<<<CONTENT\nx\nCONTENT>>>',
    ):
        assert parse_turn(reply, raw_blocks=True) == parse_turn(reply, raw_blocks=False)


def test_raw_multi_call_order():
    reply = write_block("a.py", 'x = "1"\n') + "\n" + write_block("b.py", 'y = "2"')
    t = parse_turn(reply, raw_blocks=True)
    assert [c.name for c in t.calls] == ["write_file", "write_file"]
    assert t.calls[0].args == {"path": "a.py", "content": 'x = "1"\n'}
    assert t.calls[1].args == {"path": "b.py", "content": 'y = "2"'}


def test_raw_truncated_fixture_off_unchanged():
    kw = {"lenient": True, "first_arg": FA, "json_strings": True}
    reply = FIX["truncated_edit"]["reply"]
    assert parse_turn(reply, raw_blocks=True, **kw) == parse_turn(reply, raw_blocks=False, **kw)


def test_raw_hint_only_when_on(mock_config, scripted, ws):
    reg = ToolRegistry(default_tools())
    assert reg.describe() == reg.describe(raw_blocks=False)
    assert "<<<" not in reg.describe()
    assert reg.describe(terse=True) == reg.describe(terse=True, raw_blocks=False)
    assert "<<<" not in reg.describe(terse=True)
    assert "<<<CONTENT" in reg.describe(raw_blocks=True)
    assert "<<<OLD" in reg.describe(raw_blocks=True)
    assert "<<<" not in json.dumps(reg.schemas())
    scripted.script[:] = ["Final Answer: done"]
    run(cfg_on(mock_config, "raw_file_body"), ws)
    assert "<<<CONTENT" in scripted.calls[0].messages[0].content
    scripted.calls.clear()
    scripted.script[:] = ["Final Answer: done"]
    run(with_gates_off(mock_config, approval="auto", json_string_repair=True), ws)
    assert "<<<CONTENT" not in scripted.calls[0].messages[0].content
