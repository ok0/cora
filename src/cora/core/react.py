from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

ACTION_RE = re.compile(r"Action:\s*([A-Za-z_][A-Za-z0-9_-]*)")
DELEGATE_ACTION_LINE_RE = re.compile(r"^\s*Action:\s*delegate\s*$")


def has_delegate_action_line(text: str) -> bool:
    return any(DELEGATE_ACTION_LINE_RE.match(line) for line in text.splitlines())


FINAL_MARKER = "Final Answer:"
MAX_ACTIONS_PER_TURN = 8
INPUT_ERROR = "Action Input must be a single JSON object"
RAW_BLOCK_FIELDS: dict[str, dict[str, str]] = {
    "write_file": {"CONTENT": "content"},
    "edit_file": {"OLD": "old", "NEW": "new"},
}
RAW_LABELS: tuple[str, ...] = tuple(label for f in RAW_BLOCK_FIELDS.values() for label in f)
RAW_MARKERS = frozenset({">>>", *(f"<<<{x}" for x in RAW_LABELS), *(f"{x}>>>" for x in RAW_LABELS)})
REACT_HEADERS = ("Thought:", "Action:", "Action Input:", "Final Answer:")
RAW_RULES_HINT = (
    "A raw block cannot contain a line that is only >>>, <<<CONTENT, CONTENT>>>, <<<OLD, OLD>>>, "
    "<<<NEW or NEW>>>, or a line starting with Thought:, Action:, Action Input:, Final Answer: "
    "or Observation:; send such text as a JSON string instead."
)
RAW_UNCLOSED_ERROR = (
    "Raw block {open} was not closed correctly. End it with a line that is exactly {close} "
    "(the label, then >>>; not just >>>). " + RAW_RULES_HINT
    + " Marker-like lines in your reply: {seen}"
)
RAW_STRAY_ERROR = (
    "The line {line} is a raw block marker outside any open raw block (a block ends at its "
    "first closing line). " + RAW_RULES_HINT + " Marker-like lines in your reply: {seen}"
)
RAW_ACTION_ERROR = (
    "No tool ran: a raw block could not be matched to its Action. Write Action: only at the "
    "start of the Action line itself, never inside Thought or other text (first unclear line: "
    "{line}). Marker-like lines in your reply: {seen}"
)
RAW_STATES: dict[str, str] = {
    "text": "no raw block has opened yet in this reply",
    "block": "inside a raw block",
    "after": "outside any raw block, after one has opened",
}
RAW_LINE_CLASSES: dict[str, str] = {
    "observation": "a line (not the first) starting with Observation:",
    "close": "in a block: exactly LABEL>>> for the open block's LABEL",
    "weak": "in a block: exactly >>> or <<<LABEL for the open block's LABEL",
    "opener": "outside a block: exactly <<<LABEL for a LABEL of the last Action "
    "(write_file: CONTENT; edit_file: OLD, NEW) after its Action Input: line",
    "marker": "any other line that is exactly one of >>>, <<<CONTENT, CONTENT>>>, <<<OLD, "
    "OLD>>>, <<<NEW, NEW>>>",
    "header": "a line starting with Thought:, Action:, Action Input: or Final Answer:",
    "other": "any other line, blank lines included",
    "end": "the end of the reply",
    "end_cut": "the end of a reply cut at the output token limit",
}
RAW_ACTIONS: dict[str, str] = {
    "keep": "the line stays ReAct text",
    "stop": "the turn ends here; later lines are ignored and the end rule applies",
    "open": "a block starts; the same field given twice is an error",
    "body": "the line is block text",
    "close": "the block ends; its text is the lines between the opener and this line",
    "weak": "the block ends here only if the weak-close rule holds, else error RAW_UNCLOSED_ERROR",
    "stray": "error RAW_STRAY_ERROR",
    "unclosed": "error RAW_UNCLOSED_ERROR",
    "done": "parsing ends",
}
RAW_RULES: dict[tuple[str, str], str] = {
    ("text", "observation"): "stop", ("text", "opener"): "open", ("text", "marker"): "keep",
    ("text", "header"): "keep", ("text", "other"): "keep", ("text", "end"): "done",
    ("text", "end_cut"): "done",
    ("block", "close"): "close", ("block", "weak"): "weak", ("block", "observation"): "unclosed",
    ("block", "marker"): "unclosed", ("block", "header"): "unclosed", ("block", "other"): "body",
    ("block", "end"): "unclosed", ("block", "end_cut"): "unclosed",
    ("after", "observation"): "stop", ("after", "opener"): "open", ("after", "marker"): "stray",
    ("after", "header"): "keep", ("after", "other"): "keep", ("after", "end"): "done",
    ("after", "end_cut"): "unclosed",
}
RAW_WEAK_NEXT: tuple[str, ...] = (
    "skip blank lines and lines that are exactly >>> or <<<LABEL; the block ends at the weak line "
    "only if the next line is one of:",
    "the end of the reply;",
    "a line starting with Action: or Final Answer:;",
    "a line that is exactly <<<OTHER for another LABEL of the same Action (OLD, then NEW);",
    "a line starting with Thought: whose next non-blank line starts with Action: or Final Answer:.",
)
RAW_ATTACH_RULES: tuple[str, ...] = (
    "marker lines are compared after removing whitespace at both ends",
    "a block belongs to the last Action: before its opener; every Action: up to the last "
    "block's Action must start its own line, before and after lenient repair, else error "
    "RAW_ACTION_ERROR",
    "a block's text keeps its own line breaks; one CR left at its end by a CRLF line break "
    "is dropped",
)
MARKER_LINES_MAX = 5
MARKER_LINE_CHARS = 60
RAW_DUPLICATE_ERROR = (
    "{tool}: '{field}' was given twice (in the JSON object and as a raw block, "
    "or in two raw blocks); give it once."
)
ESCAPE_HINT = 'Inside JSON strings escape every " as \\" and every \\ as \\\\.'
RAW_HINT = (
    'For write_file and edit_file you can send the text verbatim instead: '
    'Action Input: {"path": "..."} '
    "then <<<CONTENT ... CONTENT>>> (write_file) or <<<OLD ... OLD>>> and <<<NEW ... NEW>>> "
    "(edit_file), each marker on its own line."
)
EXCERPT_HALF = 30
FINAL_RE = re.compile(r"^[ \t]*Final Answer:", re.M)
TRUNCATED_ERROR = (
    "Your reply was cut off at the {n}-token output limit before the Action Input JSON was "
    "closed, so no tool ran. Use shorter replies: create a large file in parts (write_file "
    "with the first part, then write_file with append=true for each further part) or make "
    "several small edit_file edits."
)


TRUNCATED_LOCATED_NOTE = (
    " Send one Action per reply and do not repeat the same file body within a reply."
)


def truncated_error(max_tokens: int, *, located: bool = False, cause: str | None = None) -> str:
    msg = TRUNCATED_ERROR.format(n=max_tokens)
    if not located:
        return msg
    msg += TRUNCATED_LOCATED_NOTE
    return msg if cause is None else msg + "\n" + cause

FirstArg = Callable[[str], str | None]

_JSON_ESCAPES = '"\\/bfnrt'
_HEX = frozenset("0123456789abcdefABCDEF")
_CTRL_ESCAPES = {"\n": "\\n", "\t": "\\t", "\r": "\\r"}


@dataclass(frozen=True)
class ParsedStep:
    thought: str
    action: str | None
    action_input: Any
    final_answer: str | None
    error: str | None
    repaired: tuple[str, ...] = ()


def _extract_thought(text: str) -> str:
    idx = text.find("Thought:")
    if idx == -1:
        return ""
    body = text[idx + len("Thought:") :]
    ends = [i for i in (body.find("Action:"), body.find("Final Answer:")) if i != -1]
    if ends:
        body = body[: min(ends)]
    return body.strip()


def _parse_step_strict(text: str) -> ParsedStep:
    text = text.split("\nObservation:")[0]
    thought = _extract_thought(text)
    match = ACTION_RE.search(text)
    if match:
        action = match.group(1)
        idx = text.find("Action Input:")
        if idx != -1:
            brace = text.find("{", idx)
            if brace != -1:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(text[brace:])
                except json.JSONDecodeError:
                    pass
                else:
                    return ParsedStep(thought, action, obj, None, None)
        return ParsedStep(thought, action, None, None, INPUT_ERROR)
    m = FINAL_RE.search(text)
    if m:
        final = text[m.end() :].strip()
        return ParsedStep(thought, None, None, final, None)
    return ParsedStep(
        thought,
        None,
        None,
        None,
        "Invalid format: respond with 'Action:' + 'Action Input:' or 'Final Answer:'",
    )


class FinalAnswerFilter:
    def __init__(self) -> None:
        self._buf = ""
        self._start: int | None = None
        self._emitted = 0
        self._blocked = False

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        if self._blocked:
            return ""
        if self._start is None:
            fm = FINAL_RE.search(self._buf)
            am = ACTION_RE.search(self._buf)
            if am is not None and (fm is None or am.start() < fm.start()):
                self._blocked = True
                return ""
            if fm is None:
                return ""
            self._start = fm.end()
            self._emitted = self._start
        pending = self._buf[self._emitted :]
        if self._emitted == self._start:
            stripped = pending.lstrip()
            if not stripped:
                return ""
            self._emitted += len(pending) - len(stripped)
            pending = stripped
        self._emitted += len(pending)
        return pending


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: Any


@dataclass(frozen=True)
class ParsedTurn:
    thought: str
    calls: tuple[ToolCall, ...]
    final_answer: str | None
    error: str | None
    dropped: int = 0
    repaired: tuple[str, ...] = ()


def _decode_input(segment: str) -> Any:
    idx = segment.find("Action Input:")
    if idx == -1:
        return None
    brace = segment.find("{", idx)
    if brace == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(segment[brace:])
    except json.JSONDecodeError:
        return None
    return obj


def _parse_turn_strict(text: str, max_calls: int) -> ParsedTurn:
    text = text.split("\nObservation:")[0]
    thought = _extract_thought(text)
    matches = list(ACTION_RE.finditer(text))
    if not matches:
        step = _parse_step_strict(text)
        return ParsedTurn(thought, (), step.final_answer, step.error)
    calls = [
        ToolCall(
            m.group(1),
            _decode_input(
                text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            ),
        )
        for i, m in enumerate(matches)
    ]
    if len(calls) == 1 and calls[0].args is None:
        return ParsedTurn(thought, (), None, INPUT_ERROR)
    return ParsedTurn(thought, tuple(calls[:max_calls]), None, None, max(0, len(calls) - max_calls))


def _turn_rejected(p: ParsedTurn) -> bool:
    return p.error is not None or any(c.args is None for c in p.calls)


def _marker_lines(text: str) -> str:
    found: list[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("<<<") or ">>>" in s:
            found.append(s[:MARKER_LINE_CHARS])
            if len(found) == MARKER_LINES_MAX:
                break
    return " | ".join(found) if found else "none"


def _raw_line_class(line: str, i: int, state: str, label: str, opener: bool) -> str:
    s = line.strip()
    if i > 0 and line.startswith("Observation:"):
        return "observation"
    if state == "block":
        if s == f"{label}>>>":
            return "close"
        if s in (">>>", f"<<<{label}"):
            return "weak"
    elif opener:
        return "opener"
    if s in RAW_MARKERS:
        return "marker"
    if line.startswith(REACT_HEADERS):
        return "header"
    return "other"


def _weak_close_next(lines: list[str], i: int, tool: str, label: str) -> int | None:
    echo = (">>>", f"<<<{label}")
    k = i + 1
    while k < len(lines) and (not lines[k].strip() or lines[k].strip() in echo):
        k += 1
    if k == len(lines):
        return k
    nxt = lines[k]
    siblings = {f"<<<{m}" for m in RAW_BLOCK_FIELDS[tool] if m != label}
    if nxt.startswith(("Action:", "Final Answer:")) or nxt.strip() in siblings:
        return k
    if nxt.startswith("Thought:"):
        m = k + 1
        while m < len(lines) and not lines[m].strip():
            m += 1
        if m < len(lines) and lines[m].startswith(("Action:", "Final Answer:")):
            return k
    return None


def _split_raw_blocks(
    text: str, *, truncated: bool = False
) -> tuple[str, dict[int, dict[str, str]], str | None]:
    lines = text.split("\n")
    kept: list[str] = []
    blocks: dict[int, dict[str, str]] = {}
    state, tool, label, idx, start, i = "text", "", "", -1, 0, 0
    while True:
        line = s = ""
        name, n_actions, opener = "", 0, False
        if i >= len(lines):
            cls = "end_cut" if truncated else "end"
        else:
            line = lines[i]
            s = line.strip()
            if state != "block" and s.startswith("<<<") and s in RAW_MARKERS:
                prefix = "\n".join(kept)
                ms = list(ACTION_RE.finditer(prefix))
                if ms:
                    name, n_actions = ms[-1].group(1), len(ms)
                    opener = "Action Input:" in prefix[ms[-1].end() :] and s[3:] in (
                        RAW_BLOCK_FIELDS.get(name, {})
                    )
            cls = _raw_line_class(line, i, state, label, opener)
        act = RAW_RULES[(state, cls)]
        if act == "done":
            return "\n".join(kept), blocks, None
        if act == "stop":
            i = len(lines)
            continue
        if act == "keep":
            kept.append(line)
            i += 1
            continue
        if act == "body":
            i += 1
            continue
        if act == "open":
            tool, label, idx = name, s[3:], n_actions - 1
            field = RAW_BLOCK_FIELDS[tool][label]
            if field in blocks.get(idx, {}):
                return text, {}, RAW_DUPLICATE_ERROR.format(tool=tool, field=field)
            state, start, i = "block", i + 1, i + 1
            continue
        seen = _marker_lines(text.split("\nObservation:")[0])
        if act == "stray":
            return text, {}, RAW_STRAY_ERROR.format(line=s[:MARKER_LINE_CHARS], seen=seen)
        if act == "close":
            nxt = i + 1
        elif act == "weak":
            nxt = _weak_close_next(lines, i, tool, label)
        else:
            nxt = None
        if nxt is None:
            unclosed = RAW_UNCLOSED_ERROR.format(
                open=f"<<<{label}", close=f"{label}>>>", seen=seen
            )
            return text, {}, unclosed
        body = "\n".join(lines[start:i])
        blocks.setdefault(idx, {})[RAW_BLOCK_FIELDS[tool][label]] = (
            body[:-1] if body.endswith("\r") else body
        )
        state, i = "after", nxt


def _line_start(s: str, m: re.Match[str]) -> bool:
    return m.start() == 0 or s[m.start() - 1] == "\n"


def _line_of(s: str, m: re.Match[str]) -> str:
    end = s.find("\n", m.start())
    line = s[s.rfind("\n", 0, m.start()) + 1 : end if end != -1 else len(s)]
    return line.strip()[:MARKER_LINE_CHARS]


def _owner_mismatch(kept: str, used: str, last: int) -> str | None:
    used = used.split("\nObservation:")[0]
    a = list(ACTION_RE.finditer(kept))[: last + 1]
    b = list(ACTION_RE.finditer(used))[: last + 1]
    for j, m in enumerate(a):
        if not _line_start(kept, m) or j >= len(b):
            return _line_of(kept, m)
        if not _line_start(used, b[j]) or b[j].group(1) != m.group(1):
            return _line_of(used, b[j])
    return None


def _attach_blocks(t: ParsedTurn, blocks: dict[int, dict[str, str]]) -> ParsedTurn:
    if t.error is not None:
        return t
    calls = list(t.calls)
    for i, fields in blocks.items():
        if i >= len(calls) or not isinstance(calls[i].args, dict):
            continue
        for key in fields:
            if key in calls[i].args:
                return ParsedTurn(
                    t.thought, (), None, RAW_DUPLICATE_ERROR.format(tool=calls[i].name, field=key)
                )
        calls[i] = ToolCall(calls[i].name, {**calls[i].args, **fields})
    return replace(t, calls=tuple(calls))


def _excerpt_detail(seg: str) -> str | None:
    idx = seg.find("Action Input:")
    if idx == -1:
        return "no 'Action Input:' line follows the Action"
    b = seg.find("{", idx)
    if b == -1:
        return "no JSON object follows 'Action Input:'"
    block = seg[b:]
    try:
        json.JSONDecoder().raw_decode(block)
    except json.JSONDecodeError as e:
        before = block[max(0, e.pos - EXCERPT_HALF) : e.pos]
        after = block[e.pos : e.pos + EXCERPT_HALF]
        excerpt = (before + "»" + after).replace("\r", "").replace("\n", "⏎")
        return (
            f"{e.msg} at character {e.pos} of the JSON object.\n"
            f"Near the error (» marks it): {excerpt}"
        )
    return None


def located_input_error(text: str, raw_hint: bool = False) -> str:
    text = text.split("\nObservation:")[0]
    detail: str | None = None
    for _, start, end in _segments(text):
        seg = text[start:end]
        if _decode_input(seg) is None:
            detail = _excerpt_detail(seg)
            break
    head = f"{INPUT_ERROR}: {detail}" if detail is not None else INPUT_ERROR + "."
    out = head + "\n" + ESCAPE_HINT
    if raw_hint:
        out += "\n" + RAW_HINT
    return out


def parse_step(
    text: str, *, lenient: bool = False, first_arg: FirstArg | None = None
) -> ParsedStep:
    s = _parse_step_strict(text)
    if not lenient or s.error is None:
        return s
    r = _repair(text, _parse_step_strict, lambda p: p.error is not None, first_arg)
    return r if r is not None else s


def parse_turn(
    text: str,
    max_calls: int = MAX_ACTIONS_PER_TURN,
    *,
    lenient: bool = False,
    first_arg: FirstArg | None = None,
    json_strings: bool = False,
    raw_blocks: bool = False,
    located: bool = False,
    truncated: bool = False,
) -> ParsedTurn:
    blocks: dict[int, dict[str, str]] = {}
    if raw_blocks:
        cut = text.split("\nObservation:")[0]
        text, blocks, err = _split_raw_blocks(text, truncated=truncated)
        if err is not None:
            return ParsedTurn(_extract_thought(cut), (), None, err)
    used = [text]

    def strict(x: str) -> ParsedTurn:
        used[0] = x
        return _parse_turn_strict(x, max_calls)

    t = strict(text)
    if lenient and _turn_rejected(t):
        r = _repair(
            text,
            strict,
            _turn_rejected,
            first_arg,
            repairs=(JSON_STRINGS_REPAIR, *_REPAIRS) if json_strings else None,
        )
        if r is not None:
            t = r
        else:
            used[0] = text
    if blocks and t.error is None:
        bad = _owner_mismatch(text, used[0], max(blocks))
        if bad is not None:
            err = RAW_ACTION_ERROR.format(line=bad, seen=_marker_lines(cut))
            return ParsedTurn(_extract_thought(cut), (), None, err)
        t = _attach_blocks(t, blocks)
    if located and t.error == INPUT_ERROR:
        t = replace(t, error=located_input_error(text, raw_hint=raw_blocks))
    return t


def first_required_arg(parameters: Mapping[str, Any] | None) -> str | None:
    if not isinstance(parameters, Mapping):
        return None
    required = parameters.get("required")
    if isinstance(required, list) and required and isinstance(required[0], str):
        return required[0]
    props = parameters.get("properties")
    if isinstance(props, dict) and props:
        return next(iter(props))
    return None


def _unclosed_input(text: str) -> bool:
    text = _strip_fences(text, None)
    for _, start, end in _segments(text):
        seg = text[start:end]
        i = seg.find("Action Input:")
        if i == -1:
            continue
        rest = seg[i + len("Action Input:") :].lstrip()
        if rest.startswith("{") and _block_end(rest, 0, '"') == -1:
            return True
    return False


def _repair(
    text: str,
    parse: Callable[[str], Any],
    rejected: Callable[[Any], bool],
    first_arg: FirstArg | None,
    repairs: tuple[tuple[str, Callable[[str, FirstArg | None], str]], ...] | None = None,
) -> Any:
    cur = text.split("\nObservation:")[0]
    if _unclosed_input(cur):
        return None
    applied: list[str] = []
    for name, fn in repairs if repairs is not None else _REPAIRS:
        new = fn(cur, first_arg)
        if new == cur:
            continue
        cur = new
        applied.append(name)
        res = parse(cur)
        if not rejected(res):
            return replace(res, repaired=tuple(applied))
    return None


def _block_end(s: str, start: int, quotes: str) -> int:
    depth = 0
    quote: str | None = None
    i = start
    while i < len(s):
        c = s[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in quotes:
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _segments(text: str) -> list[tuple[str, int, int]]:
    matches = list(ACTION_RE.finditer(text))
    out: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), m.end(), end))
    return out


def _rewrite_failing(text: str, fn: Callable[[str, str], str | None]) -> str:
    for name, start, end in reversed(_segments(text)):
        seg = text[start:end]
        if _decode_input(seg) is not None:
            continue
        new = fn(name, seg)
        if new is not None:
            text = text[:start] + new + text[end:]
    return text


def _strip_fences(text: str, _: FirstArg | None) -> str:
    text = re.sub(r"(?m)^[ \t]*```[A-Za-z0-9_-]*[ \t]*\n?", "", text)
    return re.sub(r"(Action Input:[ \t]*)```[A-Za-z0-9_-]*", r"\1", text)


def _strip_prose(text: str, _: FirstArg | None) -> str:
    lines = text.split("\n")
    s = next(
        (
            i
            for i, ln in enumerate(lines)
            if ln.lstrip().startswith(("Thought:", "Action:", "Final Answer:"))
        ),
        None,
    )
    if s is None:
        return text
    body = "\n".join(lines[s:])
    cut = False
    if "Final Answer:" not in body:
        j = body.rfind("Action Input:")
        b = body.find("{", j) if j != -1 else -1
        if b != -1:
            e = _block_end(body, b, "\"'")
            if e != -1 and body[e:].strip():
                body = body[:e]
                cut = True
    if not cut and not "\n".join(lines[:s]).strip():
        return text
    return body


def _swap_quotes(block: str) -> str | None:
    out: list[str] = []
    dq = False
    i = 0
    while i < len(block):
        c = block[i]
        if dq:
            out.append(c)
            if c == "\\" and i + 1 < len(block):
                out.append(block[i + 1])
                i += 2
                continue
            if c == '"':
                dq = False
            i += 1
        elif c == '"':
            dq = True
            out.append(c)
            i += 1
        elif c == "'":
            j = i + 1
            buf: list[str] = []
            while j < len(block) and block[j] != "'":
                if block[j] == "\\" and j + 1 < len(block):
                    buf.append(block[j + 1])
                    j += 2
                    continue
                buf.append(block[j])
                j += 1
            if j >= len(block):
                return None
            out.append(json.dumps("".join(buf), ensure_ascii=False))
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _fix_single_quotes(text: str, _: FirstArg | None) -> str:
    def fix(name: str, seg: str) -> str | None:
        i = seg.find("Action Input:")
        if i == -1:
            return None
        b = seg.find("{", i)
        if b == -1:
            return None
        e = _block_end(seg, b, "\"'")
        if e == -1:
            return None
        block = seg[b:e]
        if "'" not in block:
            return None
        converted = _swap_quotes(block)
        if converted is None:
            return None
        return seg[:b] + converted + seg[e:]

    return _rewrite_failing(text, fix)


def _fix_trailing_commas(text: str, _: FirstArg | None) -> str:
    def fix(name: str, seg: str) -> str | None:
        i = seg.find("Action Input:")
        if i == -1:
            return None
        b = seg.find("{", i)
        if b == -1:
            return None
        e = _block_end(seg, b, '"')
        if e == -1:
            return None
        block = seg[b:e]
        out: list[str] = []
        dq = False
        changed = False
        k = 0
        while k < len(block):
            c = block[k]
            if dq:
                out.append(c)
                if c == "\\" and k + 1 < len(block):
                    out.append(block[k + 1])
                    k += 2
                    continue
                if c == '"':
                    dq = False
            elif c == '"':
                dq = True
                out.append(c)
            elif c == ",":
                n = k + 1
                while n < len(block) and block[n].isspace():
                    n += 1
                if n < len(block) and block[n] in "}]":
                    changed = True
                else:
                    out.append(c)
            else:
                out.append(c)
            k += 1
        if not changed:
            return None
        return seg[:b] + "".join(out) + seg[e:]

    return _rewrite_failing(text, fix)


def _wrap_string_input(text: str, first_arg: FirstArg | None) -> str:
    if first_arg is None:
        return text

    def fix(name: str, seg: str) -> str | None:
        i = seg.find("Action Input:")
        if i == -1:
            return None
        rest = seg[i + len("Action Input:") :].strip()
        if not rest or rest.startswith("{"):
            return None
        arg = first_arg(name)
        if arg is None:
            return None
        value: str
        if rest.startswith('"'):
            try:
                decoded, _ = json.JSONDecoder().raw_decode(rest)
            except json.JSONDecodeError:
                return None
            if not isinstance(decoded, str):
                return None
            value = decoded
        elif rest.startswith("'"):
            end = rest.find("'", 1)
            if end == -1:
                return None
            value = rest[1:end]
        else:
            value = rest.splitlines()[0].strip().strip("`")
            if any(ch in value for ch in "{}="):
                return None
        if not value:
            return None
        return seg[:i] + "Action Input: " + json.dumps({arg: value}, ensure_ascii=False) + "\n"

    return _rewrite_failing(text, fix)


def _extract_braces(text: str, _: FirstArg | None) -> str:
    def fix(name: str, seg: str) -> str | None:
        i = seg.find("Action Input:")
        start = i + len("Action Input:") if i != -1 else 0
        chosen = -1
        obj: Any = None
        k0 = seg.find("{", start)
        if k0 == -1:
            return None
        e0 = _block_end(seg, k0, '"')
        if e0 == -1:
            return None
        k = k0
        while k != -1 and k < e0:
            e = _block_end(seg, k, '"')
            if e != -1:
                try:
                    cand = json.loads(seg[k:e])
                except json.JSONDecodeError:
                    cand = None
                if isinstance(cand, dict) and (cand != {} or k == k0):
                    chosen = k
                    obj = cand
                    break
            k = seg.find("{", k + 1)
        if chosen == -1:
            return None
        if i != -1:
            head = seg[:i]
            sep = ""
        else:
            head = seg[:chosen].rstrip()
            sep = "\n"
        return head + sep + "Action Input: " + json.dumps(obj, ensure_ascii=False) + "\n"

    return _rewrite_failing(text, fix)


def _json_string_block(block: str) -> str | None:
    out: list[str] = []
    changed = False
    dq = False
    i = 0
    n = len(block)
    while i < n:
        c = block[i]
        if not dq:
            out.append(c)
            if c == '"':
                dq = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            nx = block[i + 1]
            if nx in _JSON_ESCAPES:
                out.append(block[i : i + 2])
                i += 2
                continue
            hexs = block[i + 2 : i + 6]
            if nx == "u" and len(hexs) == 4 and all(h in _HEX for h in hexs):
                out.append(block[i : i + 6])
                i += 6
                continue
            out.append("\\\\")
            changed = True
            i += 1
            continue
        if c == '"':
            dq = False
            out.append(c)
        elif ord(c) < 0x20:
            out.append(_CTRL_ESCAPES.get(c, f"\\u{ord(c):04x}"))
            changed = True
        else:
            out.append(c)
        i += 1
    return "".join(out) if changed else None


def _fix_json_strings(text: str, _: FirstArg | None) -> str:
    def fix(name: str, seg: str) -> str | None:
        i = seg.find("Action Input:")
        if i == -1:
            return None
        b = seg.find("{", i)
        if b == -1:
            return None
        e = _block_end(seg, b, '"')
        if e == -1:
            return None
        new = _json_string_block(seg[b:e])
        if new is None:
            return None
        return seg[:b] + new + seg[e:]

    return _rewrite_failing(text, fix)


_REPAIRS: tuple[tuple[str, Callable[[str, FirstArg | None], str]], ...] = (
    ("strip_fences", _strip_fences),
    ("strip_prose", _strip_prose),
    ("single_quotes", _fix_single_quotes),
    ("trailing_commas", _fix_trailing_commas),
    ("wrap_string_input", _wrap_string_input),
    ("extract_braces", _extract_braces),
)

JSON_STRINGS_REPAIR = ("json_strings", _fix_json_strings)
