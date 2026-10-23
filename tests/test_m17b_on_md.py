from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
from pathlib import Path

from conftest import act, native, tc, with_gates_off
from cora.core.agent import Agent
from cora.core.config import DelegationSettings
from cora.core.delegation import explore_registry
from cora.core.react import (
    RAW_STRAY_ERROR,
    RAW_UNCLOSED_ERROR,
    located_input_error,
    parse_turn,
    truncated_error,
)
from cora.core.tools import ApprovalPolicy
from cora.core.tools.base import ToolContext, Workspace
from cora.core.tools.builtin import EditFileTool
from cora.core.types import CompletionResponse

FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))[
    "m17b_on"
]
TASK = "make the program"
KW = {"lenient": True, "first_arg": lambda name: "path", "json_strings": True}
MARKERS = {"<<<CONTENT", "CONTENT>>>", "<<<NEW", "NEW>>>", "<<<OLD", "OLD>>>", ">>>", "<<<"}


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def cfg_on(mock_config, **keys):
    return with_gates_off(mock_config, approval="auto", json_string_repair=True, **keys)


def test_on_md_relaxed_close_s1_parses():
    for k in ("6", "8", "10", "12"):
        t = parse_turn(FIX["s1_raw_close"][k], raw_blocks=True, located=True, **KW)
        assert t.error is None, k
        assert [c.name for c in t.calls] == ["write_file"], k
        assert t.calls[0].args["path"] == "md2html.py", k
        content = t.calls[0].args["content"]
        assert len(content.split("\n")) >= 90, k
        assert not any(ln.strip() in MARKERS for ln in content.split("\n")), k


def test_on_md_relaxed_close_s3_edit_parses():
    t = parse_turn(FIX["s3_raw_old"]["6"], raw_blocks=True, located=True, **KW)
    assert t.error is None
    assert [c.name for c in t.calls] == ["edit_file"]
    args = t.calls[0].args
    assert args["path"] == "md2html.py"
    assert args["old"] and args["new"]
    assert not any(ln.strip() in MARKERS for ln in args["new"].split("\n"))


def test_on_md_bare_marker_in_body_rejected():
    msg = RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>> | CONTENT>>>"
    )
    for body in ("a\n>>>\nb", "x\n>>>\ny"):
        t = parse_turn(HEAD_WRITE + f"<<<CONTENT\n{body}\nCONTENT>>>", raw_blocks=True, **KW)
        assert t.error == msg, body
        assert t.calls == (), body


def test_on_md_relaxed_close_without_body_closer_still_unclosed():
    reply = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n<<<CONTENT\na\nb'
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT"
    )


def test_on_md_unclosed_message_spells_marker():
    msg = RAW_UNCLOSED_ERROR.format(open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT")
    assert "exactly CONTENT>>>" in msg
    assert "not just >>>" in msg
    assert msg.endswith("Marker-like lines in your reply: <<<CONTENT")


def test_on_md_unclosed_message_shows_wrong_marker_lines():
    reply = (
        'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n'
        "<<<CONTENT\na\n>>> done\nb\nCONTENT >>>"
    )
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>> done | CONTENT >>>"
    )


def test_on_md_unclosed_message_caps_marker_lines():
    head = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n'
    body = "\n".join(f"m{i} >>>" for i in range(6))
    reply = head + "<<<CONTENT\n" + body
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | m0 >>> | m1 >>> | m2 >>> | m3 >>>"
    )
    long_line = "x" * 80 + " >>>"
    assert parse_turn(head + "<<<CONTENT\n" + long_line, raw_blocks=True, **KW).error == (
        RAW_UNCLOSED_ERROR.format(
            open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | " + "x" * 60
        )
    )


def test_on_md_truncated_s1_keeps_cause(mock_config, scripted, ws):
    reply = FIX["s1_truncated"]["30"]
    cause = located_input_error(reply, raw_hint=True).split("\n")[0]
    assert "character 1277" in cause
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    r = run(cfg_on(mock_config, located_errors=True), ws)
    obs = scripted.calls[1].messages[-1].content
    assert "character 1277" in obs
    assert len(events(r, "reply_truncated")) == 1


def test_on_md_s2_marker_in_json_rejected(mock_config, scripted, ws):
    reply = FIX["s2_json_marker"]["6"]
    scripted.script[:] = [reply, "Final Answer: done"]
    run(cfg_on(mock_config, raw_file_body=True), ws)
    assert not (ws / "md2html.py").exists()
    assert "raw marker" in scripted.calls[1].messages[-1].content


def test_on_md_s2_marker_in_json_off_unchanged(mock_config, scripted, ws):
    reply = FIX["s2_json_marker"]["6"]
    scripted.script[:] = [reply, "Final Answer: done"]
    run(cfg_on(mock_config), ws)
    assert (ws / "md2html.py").read_text(encoding="utf-8").startswith("<<<CONTENT")
    assert "raw marker" not in scripted.calls[1].messages[-1].content


def test_on_md_relaxed_close_then_body_is_unclosed():
    reply = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n<<<CONTENT\nx\n>>>\ny'
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>>"
    )


HEAD_WRITE = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n'


def test_on_md_observation_line_in_block_rejected():
    t = parse_turn(
        HEAD_WRITE + "<<<CONTENT\nA\n>>>\nObservation: x\nB\nCONTENT>>>", raw_blocks=True, **KW
    )
    assert t.error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>>"
    )
    assert t.calls == ()
    t = parse_turn(
        HEAD_WRITE + "<<<CONTENT\nlog = 1\nObservation: x\nmore\nCONTENT>>>", raw_blocks=True, **KW
    )
    assert t.error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT"
    )
    assert t.calls == ()


def test_on_md_relaxed_close_then_thought_only_is_unclosed():
    reply = HEAD_WRITE + "<<<CONTENT\nline1\n>>>\nThought: footer1\nThought: footer2"
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>>"
    )


def test_on_md_relaxed_close_then_observation_is_unclosed():
    reply = HEAD_WRITE + "<<<CONTENT\nline1\n>>>\nObservation: x\nline3\nline4"
    t = parse_turn(reply, raw_blocks=True, **KW)
    assert t.error is not None
    assert "was not closed" in t.error
    assert not t.calls


def test_on_md_marker_opener_in_body_rejected():
    t = parse_turn(
        HEAD_WRITE + "<<<CONTENT\nx\n>>>\ny\n<<<CONTENT\nz\nCONTENT>>>", raw_blocks=True, **KW
    )
    assert t.error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>> | <<<CONTENT | CONTENT>>>"
    )
    assert t.calls == ()


NEXT_B = 'Thought: now b\nAction: write_file\nAction Input: {"path": "b.py"}\n'


def test_on_md_f1_hallucinated_observation_rejected(mock_config, scripted, ws):
    head = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.py"}\n'
    f1 = (
        head
        + "<<<CONTENT\nprint(1)\nObservation: file written\n"
        + NEXT_B
        + ("<<<CONTENT\nprint(2)\nCONTENT>>>")
    )
    assert parse_turn(f1, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT"
    )
    f1_weak = (
        head
        + "<<<CONTENT\nprint(1)\n>>>\nObservation: file written\n"
        + NEXT_B
        + ("<<<CONTENT\nprint(2)\nCONTENT>>>")
    )
    assert parse_turn(f1_weak, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | >>>"
    )
    scripted.script[:] = [f1, "Final Answer: done"]
    r = run(cfg_on(mock_config, raw_file_body=True), ws)
    assert not (ws / "a.py").exists()
    assert not (ws / "b.py").exists()
    assert len(events(r, "parse_error")) == 1


def test_on_md_f2_weak_then_exact_two_calls(mock_config, scripted, ws):
    f2 = (
        HEAD_WRITE
        + "<<<CONTENT\nA\n>>>\n"
        + ('Action: write_file\nAction Input: {"path": "b.py"}\n')
        + "<<<CONTENT\nB\nCONTENT>>>"
    )
    t = parse_turn(f2, raw_blocks=True, **KW)
    assert t.error is None
    assert [(c.name, c.args) for c in t.calls] == [
        ("write_file", {"path": "a.md", "content": "A"}),
        ("write_file", {"path": "b.py", "content": "B"}),
    ]
    scripted.script[:] = [f2, "Final Answer: done"]
    run(cfg_on(mock_config, raw_file_body=True), ws)
    assert (ws / "a.md").read_text(encoding="utf-8") == "A"
    assert (ws / "b.py").read_text(encoding="utf-8") == "B"


def test_on_md_f2_unclosed_then_next_action_rejected():
    reply = (
        HEAD_WRITE
        + "<<<CONTENT\nA\nThought: x\n"
        + ('Action: write_file\nAction Input: {"path": "b.py"}\n')
        + "<<<CONTENT\nB\nCONTENT>>>"
    )
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_UNCLOSED_ERROR.format(
        open="<<<CONTENT", close="CONTENT>>>", seen="<<<CONTENT | <<<CONTENT | CONTENT>>>"
    )


def test_on_md_stray_closer_after_block_rejected():
    reply = HEAD_WRITE + "<<<CONTENT\na\nCONTENT>>>\nb\nCONTENT>>>"
    assert parse_turn(reply, raw_blocks=True, **KW).error == RAW_STRAY_ERROR.format(
        line="CONTENT>>>", seen="<<<CONTENT | CONTENT>>> | CONTENT>>>"
    )
    edit = (
        'Thought: e\nAction: edit_file\nAction Input: {"path": "a.md"}\n'
        "<<<OLD\na\nOLD>>>\n<<<NEW\nb\nNEW>>>\n>>>"
    )
    assert parse_turn(edit, raw_blocks=True, **KW).error.startswith(
        "The line >>> is a raw block marker"
    )


def test_on_md_header_line_in_body_rejected():
    t = parse_turn(HEAD_WRITE + "<<<CONTENT\na\nThought: t\nb\nCONTENT>>>", raw_blocks=True, **KW)
    assert t.error.startswith("Raw block <<<CONTENT was not closed correctly")
    t = parse_turn(HEAD_WRITE + "<<<CONTENT\na\n  Thought: t\nb\nCONTENT>>>", raw_blocks=True, **KW)
    assert t.error is None
    assert t.calls[0].args["content"] == "a\n  Thought: t\nb"


def test_on_md_weak_close_then_multiline_tail_accepted():
    t = parse_turn(
        HEAD_WRITE + "<<<CONTENT\nx\n>>>\nFinal Answer: Done.\n\nSummary:", raw_blocks=True, **KW
    )
    assert t.error is None
    assert t.calls[0].args["content"] == "x"
    t = parse_turn(
        HEAD_WRITE + '<<<CONTENT\nx\n>>>\nAction: read_file\nAction Input: {\n  "path": "a.md"\n}',
        raw_blocks=True,
        **KW,
    )
    assert t.error is None
    assert [(c.name, c.args) for c in t.calls] == [
        ("write_file", {"path": "a.md", "content": "x"}),
        ("read_file", {"path": "a.md"}),
    ]


def test_on_md_truncated_reply_with_block_rejected(mock_config, scripted, ws):
    r = HEAD_WRITE + "<<<CONTENT\nx\nCONTENT>>>\nThought: more"
    t = parse_turn(r, raw_blocks=True, truncated=True, **KW)
    assert t.error.startswith("Raw block <<<CONTENT was not closed correctly")
    assert parse_turn(r, raw_blocks=True, truncated=False, **KW).error is None
    scripted.script[:] = [
        lambda req: CompletionResponse(r, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    run(cfg_on(mock_config, raw_file_body=True), ws)
    assert scripted.calls[1].messages[-1].content == "Observation: " + truncated_error(4096)
    assert not (ws / "a.md").exists()


def test_on_md_subagent_has_no_submit_plan(mock_config, ws):
    cfg = dataclasses.replace(mock_config, delegation=DelegationSettings(enabled=True))
    agent = Agent(cfg, ws, ApprovalPolicy("auto"))
    agent.ctx.plan_mode = True
    assert "submit_plan" in agent.registry_for().names()
    assert "submit_plan" not in agent.tools.names()
    assert "submit_plan" not in explore_registry(agent.tools).names()
    assert "sub_ctx.submitted_plan" not in inspect.getsource(Agent)


def test_on_md_truncated_message_has_one_action_note_and_cause():
    obs = truncated_error(4096, located=True, cause="cause line")
    assert obs.endswith("\ncause line")
    assert "Send one Action per reply" in obs
    assert "Send one Action per reply" not in truncated_error(4096)
    assert "Send one Action per reply" not in truncated_error(4096, located=False, cause="x")


def test_on_md_truncated_note_and_cause_reach_observation(mock_config, scripted, ws):
    reply = FIX["s1_truncated"]["30"]
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    run(cfg_on(mock_config, located_errors=True), ws)
    obs = scripted.calls[1].messages[-1].content
    assert "Send one Action per reply" in obs
    assert "character 1277" in obs


def test_on_md_truncated_off_has_no_note_or_cause(mock_config, scripted, ws):
    reply = FIX["s1_truncated"]["30"]
    scripted.script[:] = [
        lambda req: CompletionResponse(reply, 100, 4096, req.model, finish_reason="length"),
        "Final Answer: done",
    ]
    run(cfg_on(mock_config), ws)
    obs = scripted.calls[1].messages[-1].content
    assert "Send one Action per reply" not in obs
    assert "character 1277" not in obs


def test_on_md_edit_new_marker_refused_when_on(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"), raw_file_body=True)
    for new in ("<<<NEW\ny = 2", "y = 2\nNEW>>>"):
        r = asyncio.run(EditFileTool().run({"path": "a.py", "old": "x = 1", "new": new}, ctx))
        assert not r.ok, new
        assert "raw marker" in r.output, new
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 1\n"


def test_on_md_edit_new_marker_accepted_when_off(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"))
    r = asyncio.run(
        EditFileTool().run({"path": "a.py", "old": "x = 1", "new": "<<<NEW\ny = 2"}, ctx)
    )
    assert r.ok
    assert "raw marker" not in r.output
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "<<<NEW\ny = 2\n"


def test_on_md_delegate_child_write_not_refused(mock_config, scripted, ws):
    cfg = dataclasses.replace(
        cfg_on(mock_config, raw_file_body=True), delegation=DelegationSettings(enabled=True)
    )
    child = act("write_file", {"path": "c.py", "content": "<<<CONTENT\nx = 1\nCONTENT>>>"})
    scripted.script[:] = [
        act("delegate", {"task": "write c.py"}),
        child,
        "Final Answer: ok",
        "Final Answer: done",
    ]
    run(cfg, ws)
    assert (ws / "c.py").exists()


def test_on_md_native_protocol_has_no_raw_marker_refusal(mock_config, scripted, ws):
    body = "<<<CONTENT\nprint(1)\nCONTENT>>>"
    scripted.script[:] = [
        native(tc("write_file", {"path": "n.py", "content": body})),
        CompletionResponse("done", 10, 5, "mock/cheap"),
    ]
    run(cfg_on(mock_config, tool_protocol="native", raw_file_body=True), ws)
    assert (ws / "n.py").exists()
    for m in scripted.calls[1].messages:
        assert "raw marker" not in str(m.content)


def test_on_md_native_prompt_ignores_raw_key(mock_config, scripted, ws):
    systems = []
    for raw in (False, True):
        scripted.script[:] = [CompletionResponse("Final Answer: done", 10, 5, "mock/cheap")]
        scripted.calls.clear()
        run(cfg_on(mock_config, tool_protocol="native", raw_file_body=raw), ws)
        systems.append(scripted.calls[0].messages[0].content)
    assert systems[0] == systems[1]
    for needle in ("<<<CONTENT", "<<<OLD", "<<<NEW", "CONTENT>>>", "OLD>>>", "NEW>>>"):
        assert needle not in systems[1], needle
        assert all(needle not in str(m.content) for m in scripted.calls[0].messages), needle
        assert needle not in str(scripted.calls[0].tools), needle


F1_ACTION = ('Sure, calling Action: foo now.\nAction: write_file\nAction Input: {"path":"a.py"}\n'
             '<<<CONTENT\nA\nCONTENT>>>\nAction: write_file\nAction Input: {"path":"b.py"}\n'
             '<<<CONTENT\nB\nCONTENT>>>')
TRUNC_TEXT = (
    "Your reply was cut off at the 4096-token output limit before the Action Input JSON was "
    "closed, so no tool ran. Use shorter replies: create a large file in parts (write_file "
    "with the first part, then write_file with append=true for each further part) or make "
    "several small edit_file edits."
)
TRUNC_NOTE = " Send one Action per reply and do not repeat the same file body within a reply."


def test_on_md_prose_action_before_blocks_rejected(mock_config, scripted, ws):
    scripted.script[:] = [F1_ACTION, "Final Answer: done"]
    r = run(cfg_on(mock_config, raw_file_body=True), ws)
    assert not (ws / "a.py").exists()
    assert not (ws / "b.py").exists()
    assert len(events(r, "parse_error")) == 1
    assert (
        "No tool ran: a raw block could not be matched to its Action."
        in scripted.calls[1].messages[-1].content
    )


def test_on_md_safe_prose_before_blocks_accepted(mock_config, scripted, ws):
    safe = "Sure, here is the file.\n" + F1_ACTION.split("\n", 1)[1]
    scripted.script[:] = [safe, "Final Answer: done"]
    run(cfg_on(mock_config, raw_file_body=True), ws)
    assert (ws / "a.py").read_text(encoding="utf-8") == "A"
    assert (ws / "b.py").read_text(encoding="utf-8") == "B"


def test_on_md_truncated_without_location_has_no_cause(mock_config, scripted, ws):
    scripted.script[:] = [
        lambda req: CompletionResponse(
            "Thought: still thinking", 100, 4096, req.model, finish_reason="length"
        ),
        "Final Answer: done",
    ]
    r = run(cfg_on(mock_config, located_errors=True), ws)
    assert len(events(r, "reply_truncated")) == 1
    assert scripted.calls[1].messages[-1].content == "Observation: " + TRUNC_TEXT + TRUNC_NOTE
