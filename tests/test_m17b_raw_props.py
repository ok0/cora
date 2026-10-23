import random

import pytest

from cora.core.react import RAW_BLOCK_FIELDS, parse_turn

SEED = 20261017
N_CASES = 3000
FIELD = {label: field for f in RAW_BLOCK_FIELDS.values() for label, field in f.items()}
CLEAN = (
    "x = 1",
    '    s = "a\\\\b"  # q',
    "",
    "   ",
    ">>> f(1)",
    "a >>> b",
    "<<<FOO",
    "FOO>>>",
    "  Thought: indented",
    "    Action: indented",
    "<<< CONTENT",
    "CONTENT >>>",
    "def f():",
    "    return {}",
    "Observation (no colon)",
    "log: Observation: x",
)
TRICKY = (
    ">>>",
    "  >>>  ",
    "<<<CONTENT",
    "CONTENT>>>",
    "<<<OLD",
    "OLD>>>",
    "<<<NEW",
    "NEW>>>",
    "Observation: ok",
    "Thought: t",
    "Action: run_shell",
    "Final Answer: f",
    "Action Input: {}",
)
MOVED = ("Action:", "Final Answer:", "Thought:")
CLOSERS = ("exact", "weak>>>", "weak<<<", "none")
BETWEENS = ("", "blank", "observation", "prose")
TOOLS = ("write_file", "edit_file", "write_file", "edit_file", "read_file", "run_shell")
PADS = ("", "", " ", "\t")
PREFIX_SAFE = ("Sure, here is the file.", "", "   ", "I had a Thought: about it",
               "Use <<<CONTENT blocks for text.", "<<<CONTENT", ">>>", "CONTENT>>>",
               "  Thought: indented note", "> quoted", "**Plan**")
PREFIX_ACTION = ("Sure, calling Action: foo now.", "Here's the plan (see Action: below)",
                 "**Action: plan**", "Next Action: read_file maybe", "  Action: write_file",
                 "I will use Action:write_file next.")
BETWEEN_SAFE = ("Sure, here is the file.", "I had a Thought: about it",
                "Use <<<CONTENT blocks for text.", "  Thought: indented note", "> quoted")
BLOCK_FIELDS = {"content", "old", "new"}
ACTION_ERR = "No tool ran: a raw block could not be matched to its Action."
OTHER_BROKEN = (("read_file", "{'path': 'r.txt'}"), ("run_shell", '{"command": "echo hi",}'),
                ("read_file", "r.txt"), ("read_file", '```json\n{"path": "r.txt"}\n```'))
TAILS = ("", "final", "thought_final", "thought_only", "observation")
TAIL_LINES = {
    "": [],
    "final": ["Final Answer: ok"],
    "thought_final": ["Thought: done", "Final Answer: ok"],
    "thought_only": ["Thought: done"],
    "observation": ["Observation: ok", "Thought: more"],
}
KW = {"first_arg": lambda name: "path", "json_strings": True, "located": True}
OTHER = (
    ("run_shell", '{"command": "echo hi"}'),
    ("read_file", '{"path": "r.txt"}'),
    ("write_file", '{"path": "w.py", "content": "x = 1"}'),
    ("edit_file", '{"path": "w.py", "old": "a", "new": "b"}'),
)
U = "Raw block <<<CONTENT was not closed correctly"
S = "The line >>> is a raw block marker"
H = 'Thought: w\nAction: write_file\nAction Input: {"path": "a.md"}\n'
E = 'Thought: e\nAction: edit_file\nAction Input: {"path": "a.md"}\n'
R = 'Thought: t\nAction: run_shell\nAction Input: {"command": "echo"}\n'


def _weak(label):
    return (">>>", f"<<<{label}")


def _axiom_case(body, label, closer, siblings) -> bool:
    s = [ln.strip() for ln in body]
    if f"{label}>>>" in s:
        c = s.index(f"{label}>>>")
        if closer == "none" or any(ln.startswith("Observation:") for ln in body[c + 1 :]):
            return True
    for i, x in enumerate(s):
        if x not in _weak(label):
            continue
        j = i + 1
        while j < len(s) and (s[j] == "" or s[j] in _weak(label)):
            j += 1
        if j == len(s):
            if closer != "exact":
                return True
        elif body[j].startswith(MOVED) or s[j] in {f"<<<{m}" for m in siblings}:
            return True
    return False


def gen_case(rng, *, tricky=True, closers=CLOSERS, betweens=BETWEENS, tails=TAILS, tools=TOOLS):
    p = rng.choice((0.0, 0.15, 0.4)) if tricky else 0.0
    sep = rng.choice(("\n", "\n", "\r\n"))
    lines, intended, stopped = [], [], False
    n = rng.randint(1, 3)
    for k in range(n):
        tool = rng.choice(tools)
        if tool == "run_shell":
            key, val = "command", f"echo {k}"
        else:
            key, val = "path", rng.choice((f"p{k}.py", "same.py"))
        if rng.random() < 0.3:
            ai = ["Action Input: {", f'  "{key}": "{val}"', "}"]
        else:
            ai = [f'Action Input: {{"{key}": "{val}"}}']
        lines += [f"Thought: step {k}", f"Action: {tool}", *ai]
        args = {key: val}
        labels = tuple(RAW_BLOCK_FIELDS.get(tool, {}))
        for label in labels:
            closer = rng.choice(closers)
            siblings = [m for m in labels if m != label]
            body = ["x = 1"]
            for _ in range(20):
                cand = [rng.choice(TRICKY) if rng.random() < p else rng.choice(CLEAN)
                        for _ in range(rng.randint(0, 4))]
                if not _axiom_case(cand, label, closer, siblings):
                    body = cand
                    break
            lines += [rng.choice(PADS) + f"<<<{label}" + rng.choice(PADS), *body]
            if closer == "exact":
                lines.append(rng.choice(PADS) + f"{label}>>>" + rng.choice(PADS))
            elif closer != "none":
                lines.append(">>>" if closer == "weak>>>" else f"<<<{label}")
                lines += [rng.choice(_weak(label)) for _ in range(rng.choice((0, 0, 1, 2)))]
            args[FIELD[label]] = sep.join(body)
        if not stopped:
            intended.append((tool, args))
        if k < n - 1:
            b = rng.choice(betweens)
            if b == "blank":
                lines.append("")
            elif b == "observation":
                lines += ["Observation: done", "more text"]
                stopped = True
            elif b == "prose":
                lines.append(rng.choice(BETWEEN_SAFE))
    lines += TAIL_LINES[rng.choice(tails)]
    return sep.join(lines), intended


def gen_plain(rng):
    lines = [rng.choice(PREFIX_SAFE + PREFIX_ACTION) for _ in range(rng.choice((0, 0, 1, 2)))]
    for k in range(rng.randint(1, 3)):
        name, args = rng.choice(OTHER + OTHER_BROKEN)
        lines += [f"Thought: p{k}", f"Action: {name}", f"Action Input: {args}"]
        pool = CLEAN if name in RAW_BLOCK_FIELDS else CLEAN + TRICKY
        lines += [rng.choice(pool) for _ in range(rng.randint(0, 3))]
        if rng.random() < 0.15:
            lines.append("Observation: x")
    if rng.random() < 0.3:
        lines.append("Final Answer: ok")
    return "\n".join(lines)


ROW_EXAMPLES = {
    ("text", "observation"): [
        (
            H + "x\nObservation: o\n<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md"})]),
        )
    ],
    ("text", "opener"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("text", "marker"): [(R + ">>>\nCONTENT>>>\n<<<CONTENT", False, ("off", None))],
    ("text", "header"): [
        (
            H + "Thought: more\n<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("text", "other"): [
        (
            H + "prose\n<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("text", "end"): [
        ('Thought: t\nAction: read_file\nAction Input: {"path": "a"}', False, ("off", None))
    ],
    ("text", "end_cut"): [
        ('Thought: t\nAction: read_file\nAction Input: {"path": "a"}', True, ("off", None))
    ],
    ("block", "close"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("block", "weak"): [
        (
            H + "<<<CONTENT\nb\n>>>\nFinal Answer: d",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        ),
        (H + "<<<CONTENT\nb\n>>>\nc", False, ("err", U)),
    ],
    ("block", "observation"): [
        (H + "<<<CONTENT\nb\nObservation: o\nCONTENT>>>", False, ("err", U))
    ],
    ("block", "marker"): [(H + "<<<CONTENT\nb\nNEW>>>\nCONTENT>>>", False, ("err", U))],
    ("block", "header"): [(H + "<<<CONTENT\nb\nAction: x\nCONTENT>>>", False, ("err", U))],
    ("block", "other"): [
        (
            H + "<<<CONTENT\n\n  Thought: t\n>>> f()\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "\n  Thought: t\n>>> f()"})]),
        )
    ],
    ("block", "end"): [(H + "<<<CONTENT\nb", False, ("err", U))],
    ("block", "end_cut"): [(H + "<<<CONTENT\nb", True, ("err", U))],
    ("after", "observation"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>\nObservation: o\nAction: write_file\n"
            'Action Input: {"path": "c.md"}\n<<<CONTENT\nc\nCONTENT>>>',
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("after", "opener"): [
        (
            E + "<<<OLD\na\nOLD>>>\n<<<NEW\nb\nNEW>>>",
            False,
            ("calls", [("edit_file", {"path": "a.md", "old": "a", "new": "b"})]),
        ),
        (
            E + "<<<OLD\na\nOLD>>>\n<<<OLD\nb\nOLD>>>",
            False,
            ("err", "edit_file: 'old' was given twice"),
        ),
    ],
    ("after", "marker"): [(H + "<<<CONTENT\nb\nCONTENT>>>\n>>>", False, ("err", S))],
    ("after", "header"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>\nThought: done\nmore thought",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("after", "other"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>\nprose",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("after", "end"): [
        (
            H + "<<<CONTENT\nb\nCONTENT>>>",
            False,
            ("calls", [("write_file", {"path": "a.md", "content": "b"})]),
        )
    ],
    ("after", "end_cut"): [(H + "<<<CONTENT\nb\nCONTENT>>>", True, ("err", U))],
}

WEAK_NEXT_CASES = [
    ("", True),
    ('Action: read_file\nAction Input: {"path": "a"}', True),
    ("Final Answer: d", True),
    ('Thought: t\nAction: read_file\nAction Input: {"path": "a"}', True),
    ("Thought: t\n\nFinal Answer: d", True),
    (">>>\n<<<CONTENT\n\nFinal Answer: d", True),
    ("Thought: t", False),
    ("Thought: t\nmore\nFinal Answer: d", False),
    ("Observation: o", False),
    ("c", False),
    ("CONTENT>>>", False),
    ("<<<OLD", False),
]


def _calls(t):
    return [(c.name, c.args) for c in t.calls]


def _contained(t, intended, label):
    if t.error is not None:
        assert t.calls == (), label
    for c in t.calls:
        if isinstance(c.args, dict) and BLOCK_FIELDS & set(c.args):
            assert (c.name, c.args) in intended, f"{label}\ngot {_calls(t)}\nexpected {intended}"


@pytest.mark.parametrize("lenient", [False, True])
def test_raw_soundness_property(lenient):
    rng = random.Random(SEED + int(lenient))
    accepted = 0
    for case in range(N_CASES):
        text, intended = gen_case(rng)
        t = parse_turn(text, lenient=lenient, raw_blocks=True, **KW)
        _contained(t, intended, f"case {case}\n{text}")
        if t.error is None:
            accepted += 1
            got = _calls(t)
            assert got == intended, f"case {case}\n{text}\ngot {got}\nexpected {intended}"
    assert accepted >= 200


def test_raw_truncated_property():
    rng = random.Random(SEED + 2)
    for case in range(N_CASES):
        text, _ = gen_case(rng)
        lines = text.split("\n")
        cut = "\n".join(lines[: rng.randint(1, len(lines))])
        t = parse_turn(cut, lenient=True, raw_blocks=True, truncated=True, **KW)
        if t.error is None:
            for c in t.calls:
                if isinstance(c.args, dict):
                    assert not ({"content", "old", "new"} & set(c.args)), (
                        f"case {case}\n{cut}\n{_calls(t)}"
                    )


def test_raw_liveness_property():
    rng = random.Random(SEED + 3)
    for case in range(N_CASES):
        text, intended = gen_case(
            rng,
            tricky=False,
            closers=("exact", "weak>>>", "weak<<<"),
            betweens=("", "blank"),
            tails=("", "final", "thought_final"),
        )
        t = parse_turn(text, lenient=True, raw_blocks=True, **KW)
        assert t.error is None, f"case {case}\n{text}\n{t.error}"
        assert _calls(t) == intended, f"case {case}\n{text}\ngot {_calls(t)}\nexpected {intended}"


@pytest.mark.parametrize("lenient", [False, True])
def test_raw_liveness_with_prose_property(lenient):
    rng = random.Random(SEED + 6 + int(lenient))
    for case in range(N_CASES):
        text, intended = gen_case(
            rng,
            tricky=False,
            closers=("exact",),
            betweens=("", "blank", "prose"),
            tails=("", "final", "thought_final"),
        )
        pre = [rng.choice(PREFIX_SAFE) for _ in range(rng.randint(1, 3))]
        full = "\n".join(pre) + "\n" + text
        t = parse_turn(full, lenient=lenient, raw_blocks=True, **KW)
        assert t.error is None, f"case {case}\n{full}\n{t.error}"
        assert _calls(t) == intended, f"case {case}\n{full}\ngot {_calls(t)}\nexpected {intended}"


@pytest.mark.parametrize("lenient", [False, True])
def test_raw_prefix_action_property(lenient):
    rng = random.Random(SEED + 8 + int(lenient))
    rejected_cases = 0
    safe_cases = 0
    for case in range(N_CASES):
        text, intended = gen_case(rng)
        pre = [rng.choice(PREFIX_SAFE + PREFIX_ACTION) for _ in range(rng.randint(1, 3))]
        full = "\n".join(pre) + "\n" + text
        t = parse_turn(full, lenient=lenient, raw_blocks=True, **KW)
        base = parse_turn(text, lenient=lenient, raw_blocks=True, **KW)
        label = f"case {case}\n{full}"
        _contained(t, intended, label)
        has_block = base.error is None and any(
            isinstance(c.args, dict) and BLOCK_FIELDS & set(c.args) for c in base.calls
        )
        has_action_prefix = any(x in PREFIX_ACTION for x in pre)
        if has_action_prefix and has_block:
            rejected_cases += 1
            assert t.error is not None and t.error.startswith(ACTION_ERR), f"{label}\n{t.error}"
            assert t.calls == (), label
        if not has_action_prefix and base.error is None and base.repaired == ():
            safe_cases += 1
            assert t.error is None, f"{label}\n{t.error}"
            assert _calls(t) == _calls(base), label
    assert rejected_cases >= 200
    assert safe_cases >= 200


@pytest.mark.parametrize("lenient", [False, True])
def test_raw_parity_without_blocks(lenient):
    rng = random.Random(SEED + 4 + int(lenient))
    kw = {"lenient": lenient, "first_arg": lambda name: "path", "json_strings": True}
    for case in range(N_CASES):
        text = gen_plain(rng)
        assert parse_turn(text, raw_blocks=True, **kw) == parse_turn(
            text, raw_blocks=False, **kw
        ), f"case {case}\n{text}"


def test_raw_rules_table_shape():
    from cora.core.react import RAW_ACTIONS, RAW_LINE_CLASSES, RAW_RULES, RAW_STATES, RAW_WEAK_NEXT

    outside = ("observation", "opener", "marker", "header", "other", "end", "end_cut")
    inside = ("close", "weak", "observation", "marker", "header", "other", "end", "end_cut")
    assert set(RAW_RULES) == {(s, c) for s in ("text", "after") for c in outside} | {
        ("block", c) for c in inside
    }
    assert set(RAW_RULES.values()) == set(RAW_ACTIONS)
    assert {c for _, c in RAW_RULES} == set(RAW_LINE_CLASSES)
    assert set(RAW_STATES) == {"text", "block", "after"}
    assert RAW_WEAK_NEXT and all(isinstance(x, str) for x in RAW_WEAK_NEXT)
    assert set(ROW_EXAMPLES) == set(RAW_RULES)


@pytest.mark.parametrize("row", sorted(ROW_EXAMPLES))
def test_raw_rule_rows(row):
    for reply, truncated, expect in ROW_EXAMPLES[row]:
        t = parse_turn(reply, raw_blocks=True, truncated=truncated)
        kind, value = expect
        if kind == "off":
            assert t == parse_turn(reply, raw_blocks=False)
        elif kind == "err":
            assert t.error is not None and t.error.startswith(value), t.error
        else:
            assert t.error is None, t.error
            assert _calls(t) == value


@pytest.mark.parametrize("tail, ok", WEAK_NEXT_CASES)
def test_raw_weak_next_cases(tail, ok):
    reply = H + "<<<CONTENT\nb\n>>>" + ("\n" + tail if tail else "")
    t = parse_turn(reply, raw_blocks=True)
    if ok:
        assert t.error is None, t.error
        assert t.calls[0].name == "write_file"
        assert t.calls[0].args["content"] == "b"
    else:
        assert t.error is not None and t.error.startswith(U), t.error


def test_raw_weak_close_edit_accepted():
    t = parse_turn(E + "<<<OLD\na\n>>>\n<<<NEW\nb\nNEW>>>", raw_blocks=True)
    assert t.error is None, t.error
    assert _calls(t) == [("edit_file", {"path": "a.md", "old": "a", "new": "b"})]
