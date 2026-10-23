from __future__ import annotations

import json
from pathlib import Path

import pytest

from cora.core.react import (
    FINAL_RE,
    INPUT_ERROR,
    FinalAnswerFilter,
    parse_step,
    parse_turn,
    truncated_error,
)
from test_lenient_parse import STEP_ROWS, TURN_ROWS

INVALID = "Invalid format: respond with 'Action:' + 'Action Input:' or 'Final Answer:'"
FIRST = {"read_file": "path", "list_files": "path", "edit_file": "path"}.get


def _fx(name: str) -> str:
    return (Path(__file__).parent / "fixtures" / "m15b" / name).read_text(encoding="utf-8")


def _act(name: str, args: dict) -> str:
    return f"Thought: t\nAction: {name}\nAction Input: {json.dumps(args)}"


def _run_filter(chunks: list[str]) -> str:
    f = FinalAnswerFilter()
    return "".join(f.feed(c) for c in chunks)


def test_truncated_error_text():
    msg = truncated_error(4096)
    assert "4096" in msg
    assert "no tool ran" in msg
    assert "write_file" in msg
    assert "append=true" in msg
    assert msg != INPUT_ERROR


def test_rest_notes_cut_never_empty_call():
    fx = _fx("cheap_rest_notes_r0_cut.txt")
    strict = parse_step(fx, lenient=False)
    assert parse_step(fx, lenient=True, first_arg=FIRST) == strict
    turn = parse_turn(fx, lenient=True, first_arg=FIRST)
    assert parse_turn(fx, lenient=False) == turn
    assert turn.calls == ()
    assert turn.error == INPUT_ERROR
    assert turn.repaired == ()
    assert all(c.args != {} for c in turn.calls)


def test_strong_md_cut_not_repaired():
    fx = _fx("strong_md_to_html_cut.txt")
    strict = parse_step(fx, lenient=False)
    assert parse_step(fx, lenient=True, first_arg=FIRST) == strict
    turn = parse_turn(fx, lenient=True, first_arg=FIRST)
    assert parse_turn(fx, lenient=False) == turn
    assert turn.calls == ()
    assert turn.error == INPUT_ERROR
    assert turn.repaired == ()
    assert all(c.args != {} for c in turn.calls)


def test_unclosed_inside_fence_not_repaired():
    text = (
        'Thought: t\nAction: edit_file\nAction Input:\n```json\n{"path": "a.py", "new": "x = {}\\n'
    )
    t = parse_turn(text, lenient=True, first_arg=FIRST)
    assert t.error == INPUT_ERROR
    assert t.calls == ()


def test_inner_empty_object_not_chosen():
    text = 'Thought: t\nAction: edit_file\nAction Input: {path: "a.py", "new": "d = {}"}'
    t = parse_turn(text, lenient=True, first_arg=FIRST)
    assert all(c.args != {} for c in t.calls)
    s = parse_step(text, lenient=True, first_arg=FIRST)
    assert s.action_input != {}


@pytest.mark.parametrize("name", ["cheap_todo_r0_final.txt", "cheap_todo_r1_final.txt"])
def test_quoted_final_answer_not_final(name):
    fx = _fx(name)
    assert parse_step(fx).final_answer is None
    assert parse_turn(fx, lenient=True, first_arg=FIRST).final_answer is None
    assert parse_turn(fx).final_answer is None


def test_inline_final_answer_rejected():
    s = parse_step("Thought: see the 'Final Answer:' error")
    assert s.final_answer is None
    assert s.error == INVALID


def test_line_start_final_answer():
    assert parse_step("Thought: done\nFinal Answer: 42").final_answer == "42"
    assert parse_step("Thought: done\n   Final Answer: ok").final_answer == "ok"
    assert parse_step("Final Answer: x").final_answer == "x"
    assert FINAL_RE.search("Thought: done\nFinal Answer: 42") is not None


def test_action_beats_later_final():
    text = _act("list_files", {"path": "."}) + "\nFinal Answer: no"
    t = parse_turn(text)
    assert len(t.calls) == 1
    assert t.calls[0].name == "list_files"
    assert t.calls[0].args == {"path": "."}
    assert t.final_answer is None


def test_filter_line_start():
    assert _run_filter(["Thought: the 'Final Answer:' error. I"]) == ""
    assert _run_filter(["Thought: x\nFinal Ans", "wer: hi"]) == "hi"
    assert _run_filter(["Thought: x\n  Final Answer: ok"]) == "ok"
    assert _run_filter(["Thought: x\nAction: read_file\n", "Final Answer: no"]) == ""


@pytest.mark.parametrize(
    "id_,text,action,action_input,repaired", STEP_ROWS, ids=[r[0] for r in STEP_ROWS]
)
def test_m12_step_rows_unchanged(id_, text, action, action_input, repaired):
    s = parse_step(text, lenient=True, first_arg=FIRST)
    assert s.error is None
    assert s.action == action
    assert s.action_input == action_input
    assert s.repaired == repaired


@pytest.mark.parametrize("id_,text,calls,repaired", TURN_ROWS, ids=[r[0] for r in TURN_ROWS])
def test_m12_turn_rows_unchanged(id_, text, calls, repaired):
    t = parse_turn(text, lenient=True, first_arg=FIRST)
    assert t.error is None
    assert [(c.name, c.args) for c in t.calls] == calls
    assert t.repaired == repaired
