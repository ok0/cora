from __future__ import annotations

import asyncio

import pytest

import cora.core.react as react
from cora.core.react import ToolCall, parse_turn, truncated_error
from cora.core.tools import ApprovalPolicy
from cora.core.tools.base import ToolContext, Workspace
from cora.core.tools.builtin import EditFileTool, WriteFileTool

HINT = ("A raw block cannot contain a line that is only >>>, <<<CONTENT, CONTENT>>>, <<<OLD, "
        "OLD>>>, <<<NEW or NEW>>>, or a line starting with Thought:, Action:, Action Input:, "
        "Final Answer: or Observation:; send such text as a JSON string instead.")


def UNCLOSED(op, cl, seen):
    return (f"Raw block {op} was not closed correctly. End it with a line that is exactly {cl} "
            f"(the label, then >>>; not just >>>). {HINT} Marker-like lines in your reply: {seen}")


def STRAY(line, seen):
    return (f"The line {line} is a raw block marker outside any open raw block (a block ends at "
            f"its first closing line). {HINT} Marker-like lines in your reply: {seen}")


def ACTION(line, seen):
    return ("No tool ran: a raw block could not be matched to its Action. Write Action: only at "
            "the start of the Action line itself, never inside Thought or other text (first "
            f"unclear line: {line}). Marker-like lines in your reply: {seen}")


def DUP(tool, field):
    return (f"{tool}: '{field}' was given twice (in the JSON object and as a raw block, or in "
            "two raw blocks); give it once.")


def REFUSE(tool, field, label):
    return (f"{tool} failed: '{field}' starts or ends with a raw marker line, which was written "
            "inside the JSON string. Put the text after the closing } of Action Input, between "
            f"a line <<<{label} and a line {label}>>>, and do not also give '{field}' in the JSON.")


TRUNC = ("Your reply was cut off at the 4096-token output limit before the Action Input JSON was "
         "closed, so no tool ran. Use shorter replies: create a large file in parts (write_file "
         "with the first part, then write_file with append=true for each further part) or make "
         "several small edit_file edits.")
NOTE = " Send one Action per reply and do not repeat the same file body within a reply."
H = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n'
E = 'Thought: e\nAction: edit_file\nAction Input: {"path": "a.md"}\n'
KW = {"lenient": True, "first_arg": lambda name: "path", "json_strings": True}
F1 = ('Sure, calling Action: foo now.\nAction: write_file\nAction Input: {"path":"a.py"}\n'
      '<<<CONTENT\nA\nCONTENT>>>\nAction: write_file\nAction Input: {"path":"b.py"}\n'
      '<<<CONTENT\nB\nCONTENT>>>')
SEEN4 = "<<<CONTENT | CONTENT>>> | <<<CONTENT | CONTENT>>>"
TWO = ('Action: write_file\nAction Input: {"path": "a.md",}\n<<<CONTENT\nA\nCONTENT>>>\n'
       'Action: write_file\nAction Input: {"path": "b.md"}\n<<<CONTENT\nB\nCONTENT>>>')


def p(x, **k):
    return parse_turn(x, raw_blocks=True, **k)


def _calls(t):
    return [(c.name, c.args) for c in t.calls]


def test_exact_hint_constant():
    assert react.RAW_RULES_HINT == HINT


def test_exact_raw_hint_in_input_error():
    t = parse_turn(
        'Thought: w\nAction: write_file\nAction Input: {"path": "a.md",}\n'
        "<<<CONTENT\nb\nCONTENT>>>",
        raw_blocks=True,
        located=True,
    )
    raw_hint = (
        'For write_file and edit_file you can send the text verbatim instead: '
        'Action Input: {"path": "..."} '
        "then <<<CONTENT ... CONTENT>>> (write_file) or <<<OLD ... OLD>>> and <<<NEW ... NEW>>> "
        "(edit_file), each marker on its own line."
    )
    assert t.error is not None
    assert t.error.endswith("\n" + raw_hint)


def test_exact_unclosed():
    assert p(H + "<<<CONTENT\nb").error == UNCLOSED("<<<CONTENT", "CONTENT>>>", "<<<CONTENT")
    assert p(E + "<<<OLD\na\nOLD>>>\n<<<NEW\nb").error == UNCLOSED(
        "<<<NEW", "NEW>>>", "<<<OLD | OLD>>> | <<<NEW")


def test_exact_stray():
    assert p(H + "<<<CONTENT\nb\nCONTENT>>>\n>>>").error == STRAY(
        ">>>", "<<<CONTENT | CONTENT>>> | >>>")


def test_exact_duplicate():
    assert p(E + "<<<OLD\na\nOLD>>>\n<<<OLD\nb\nOLD>>>").error == DUP("edit_file", "old")
    assert p('Thought: w\nAction: write_file\nAction Input: {"path": "a.md", "content": "j"}\n'
             '<<<CONTENT\nb\nCONTENT>>>').error == DUP("write_file", "content")


@pytest.mark.parametrize("lenient", [False, True])
def test_action_error_f1(lenient):
    t = p(F1, lenient=lenient)
    assert t.error == ACTION("Sure, calling Action: foo now.", SEEN4)
    assert t.calls == ()
    assert t.thought == ""


def test_action_error_plan_prose():
    t = p("Here's the plan (see Action: below)\n\nAction: write_file\n"
          'Action Input: {"path": "a.py"}\n<<<CONTENT\nA\nCONTENT>>>', **KW)
    assert t.error == ACTION("Here's the plan (see Action: below)", "<<<CONTENT | CONTENT>>>")


def test_action_error_in_thought():
    t = p('Thought: I will call Action: write_file twice\n'
          'Action: write_file\nAction Input: {"path": "a.md"}\n<<<CONTENT\nb\nCONTENT>>>', **KW)
    assert t.error == ACTION("Thought: I will call Action: write_file twice",
                             "<<<CONTENT | CONTENT>>>")
    assert t.thought == "I will call"


def test_action_error_line_capped():
    t = p("x" * 70 + " Action: foo" + "\n" + H + "<<<CONTENT\nb\nCONTENT>>>", **KW)
    assert t.error == ACTION("x" * 60, "<<<CONTENT | CONTENT>>>")


def test_action_after_last_block_allowed():
    r = H + "<<<CONTENT\nb\nCONTENT>>>\nDone with Action: x"
    assert _calls(p(r, **KW)) == [("write_file", {"path": "a.md", "content": "b"})]
    t = p(r)
    assert t.error is None
    assert t.calls[0] == ToolCall("write_file", {"path": "a.md", "content": "b"})
    assert t.calls[1].name == "x"
    assert t.calls[1].args is None


def test_owner_guard_deleted_call(monkeypatch):
    def drop(t, _):
        return t.replace('Action: write_file\nAction Input: {"path": "a.md",}\n', "", 1)

    monkeypatch.setattr(react, "_REPAIRS", (("drop", drop),))
    assert p(TWO, lenient=True).error == ACTION("Action: write_file", SEEN4)


def test_owner_guard_inserted_call(monkeypatch):
    def insert(t, _):
        return t.replace(
            '{"path": "a.md",}', '{"path": "a.md"}\nsee Action: z\nAction Input: {}', 1)

    monkeypatch.setattr(react, "_REPAIRS", (("insert", insert),))
    assert p(TWO, lenient=True).error == ACTION("see Action: z", SEEN4)


def test_repairs_registry_pinned():
    assert [n for n, _ in react._REPAIRS] == [
        "strip_fences", "strip_prose", "single_quotes", "trailing_commas",
        "wrap_string_input", "extract_braces",
    ], "new repair rule: re-check the I4 attachment argument in plan M17b Revision 3"
    assert react.JSON_STRINGS_REPAIR[0] == "json_strings"


def crlf(s):
    return s.replace("\n", "\r\n")


def test_crlf_block_body():
    def content(text):
        return p(text).calls[0].args["content"]

    assert content(crlf(H + "<<<CONTENT\nx = 1\ny = 2\nCONTENT>>>\n")) == "x = 1\r\ny = 2"
    assert content(crlf(H + "<<<CONTENT\nx = 1\ny = 2\n>>>\nFinal Answer: d")) == "x = 1\r\ny = 2"
    assert content(crlf(H + "<<<CONTENT\nCONTENT>>>")) == ""
    assert content(crlf(H + "<<<CONTENT\nx\n\nCONTENT>>>")) == "x\r\n"
    assert content(crlf(H) + "<<<CONTENT\r\na\r\r\nCONTENT>>>") == "a\r"
    assert _calls(p(crlf(E + "<<<OLD\na\nOLD>>>\n<<<NEW\nb\nNEW>>>"))) == [
        ("edit_file", {"path": "a.md", "old": "a", "new": "b"})]
    assert p(H + "<<<CONTENT\nx\n\nCONTENT>>>").calls[0].args["content"] == "x\n"


def test_action_input_line_in_block():
    assert p(H + '<<<CONTENT\na\nAction Input: {"x": 1}\nCONTENT>>>').error == UNCLOSED(
        "<<<CONTENT", "CONTENT>>>", "<<<CONTENT | CONTENT>>>")
    body = p(H + '<<<CONTENT\na\n  Action Input: {"x": 1}\nCONTENT>>>').calls[0].args["content"]
    assert body == 'a\n  Action Input: {"x": 1}'


def test_padded_markers():
    assert p(H + "<<<CONTENT\nb\n  CONTENT>>>").calls[0].args["content"] == "b"
    assert p(H + "<<<CONTENT\nb\n  >>>\nFinal Answer: d").calls[0].args["content"] == "b"
    assert p(H + "  <<<CONTENT \t\nb\nCONTENT>>>").calls[0].args["content"] == "b"


def test_opener_needs_action_input():
    assert _calls(p('Thought: w\nAction: write_file\n<<<CONTENT\nb\nCONTENT>>>\n'
                    'Action Input: {"path": "a.md"}')) == [("write_file", {"path": "a.md"})]


def test_observation_on_line_0_is_text():
    assert _calls(p("Observation: x\n" + H + "<<<CONTENT\nb\nCONTENT>>>")) == [
        ("write_file", {"path": "a.md", "content": "b"})]


def test_error_thought_from_cut():
    t = p('Action: write_file\nAction Input: {"path": "a.md"}\n'
          '<<<CONTENT\nb\nObservation: o\nThought: late')
    assert t.error == UNCLOSED("<<<CONTENT", "CONTENT>>>", "<<<CONTENT")
    assert t.thought == ""


def test_exact_truncated_texts():
    assert truncated_error(4096) == TRUNC
    assert truncated_error(4096, located=True) == TRUNC + NOTE
    assert truncated_error(4096, located=True, cause="c") == TRUNC + NOTE + "\nc"


def test_exact_refusals(tmp_path):
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"), raw_file_body=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    for c in (
        "<<<CONTENT\nx", "x\nCONTENT>>>", "x\n>>>", "x\nNEW>>>",
        "x\n   CONTENT>>>", "<<<CONTENT   \nx",
    ):
        r = asyncio.run(WriteFileTool().run({"path": "w.py", "content": c}, ctx))
        assert not r.ok
        assert r.output == REFUSE("write_file", "content", "CONTENT")
        assert not (tmp_path / "w.py").exists()
    for n in ("<<<NEW\ny", "y\n>>>"):
        r = asyncio.run(EditFileTool().run({"path": "a.py", "old": "x = 1", "new": n}, ctx))
        assert not r.ok
        assert r.output == REFUSE("edit_file", "new", "NEW")
    r = asyncio.run(EditFileTool().run({"path": "a.py", "old": "x = 1", "new": "y\n>>> f(1)"}, ctx))
    assert r.ok


def test_owner_guard_failed_repair_uses_strict_text(monkeypatch):
    monkeypatch.setattr(react, "_REPAIRS", (
        ("drop_and_break", lambda t, _: t.replace(
            'Action: write_file\nAction Input: {"path": "a.md",}\n', "", 1
        ).replace('{"path": "b.md"}', '{"path": "b.md",}', 1)),
    ))
    t = p(TWO, lenient=True)
    assert t.error is None
    assert _calls(t) == [
        ("write_file", None), ("write_file", {"path": "b.md", "content": "B"})]
