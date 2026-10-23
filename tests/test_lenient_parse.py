from __future__ import annotations

import asyncio

import pytest

from conftest import act, with_agent
from cora.core.agent import Agent
from cora.core.config import parse_config
from cora.core.errors import ConfigError
from cora.core.observability import read_events
from cora.core.react import INPUT_ERROR, first_required_arg, parse_step, parse_turn
from cora.core.tools import ApprovalPolicy, GitStatusTool, ListFilesTool, ReadFileTool

FIRST = {"read_file": "path", "list_files": "path"}.get
INVALID = "Invalid format: respond with 'Action:' + 'Action Input:' or 'Final Answer:'"

FENCED = 'Thought: read it\nAction: read_file\nAction Input:\n```json\n{"path": "a.py",}\n```'
NOISE = (
    "Next Action: look around first.\nThought: read it\nAction: read_file\n"
    'Action Input: {"path": "a.py"}\nThat should do it.'
)
SINGLE_QUOTES = "Thought: read it\nAction: read_file\nAction Input: {'path': 'a.py'}"
TRAILING_COMMA = 'Thought: list\nAction: list_files\nAction Input: {"path": "src",}'
STRING_INPUT = 'Thought: read it\nAction: read_file\nAction Input: "a.py"'
BARE_INPUT = "Thought: read it\nAction: read_file\nAction Input: a.py"
EMBEDDED = 'Thought: read it\nAction: read_file\nAction Input: {{"path": "a.py"}}'
MISSING_LABEL = 'Thought: read it\nAction: read_file\n{"path": "a.py"}'
BENCH_FAILURE = (
    'Thought: look around\nAction: list_files\nAction Input: "."\n'
    'Action: read_file\nAction Input: {"path": "config.py"}'
)

STEP_ROWS = [
    ("fenced", FENCED, "read_file", {"path": "a.py"}, ("strip_fences", "trailing_commas")),
    ("single_quotes", SINGLE_QUOTES, "read_file", {"path": "a.py"}, ("single_quotes",)),
    ("trailing_comma", TRAILING_COMMA, "list_files", {"path": "src"}, ("trailing_commas",)),
    ("string_input", STRING_INPUT, "read_file", {"path": "a.py"}, ("wrap_string_input",)),
    ("bare_input", BARE_INPUT, "read_file", {"path": "a.py"}, ("wrap_string_input",)),
    ("embedded_block", EMBEDDED, "read_file", {"path": "a.py"}, ("extract_braces",)),
    ("missing_label", MISSING_LABEL, "read_file", {"path": "a.py"}, ("extract_braces",)),
]

TURN_ROWS = [
    ("fenced", FENCED, [("read_file", {"path": "a.py"})], ("strip_fences", "trailing_commas")),
    ("noise", NOISE, [("read_file", {"path": "a.py"})], ("strip_prose",)),
    ("single_quotes", SINGLE_QUOTES, [("read_file", {"path": "a.py"})], ("single_quotes",)),
    ("trailing_comma", TRAILING_COMMA, [("list_files", {"path": "src"})], ("trailing_commas",)),
    ("string_input", STRING_INPUT, [("read_file", {"path": "a.py"})], ("wrap_string_input",)),
    ("bare_input", BARE_INPUT, [("read_file", {"path": "a.py"})], ("wrap_string_input",)),
    ("embedded_block", EMBEDDED, [("read_file", {"path": "a.py"})], ("extract_braces",)),
    ("missing_label", MISSING_LABEL, [("read_file", {"path": "a.py"})], ("extract_braces",)),
    (
        "bench_failure",
        BENCH_FAILURE,
        [("list_files", {"path": "."}), ("read_file", {"path": "config.py"})],
        ("wrap_string_input",),
    ),
]


@pytest.mark.parametrize(
    "id_,text,action,action_input,repaired", STEP_ROWS, ids=[r[0] for r in STEP_ROWS]
)
def test_repair_table_step(id_, text, action, action_input, repaired):
    strict = parse_step(text)
    assert strict.error is not None
    s = parse_step(text, lenient=True, first_arg=FIRST)
    assert s.error is None
    assert s.action == action
    assert s.action_input == action_input
    assert s.repaired == repaired


@pytest.mark.parametrize("id_,text,calls,repaired", TURN_ROWS, ids=[r[0] for r in TURN_ROWS])
def test_repair_table_turn(id_, text, calls, repaired):
    strict = parse_turn(text)
    assert strict.error is not None or any(c.args is None for c in strict.calls)
    t = parse_turn(text, lenient=True, first_arg=FIRST)
    assert t.error is None
    assert [(c.name, c.args) for c in t.calls] == calls
    assert t.repaired == repaired


def test_strict_accepted_is_identical():
    texts = [
        act("list_files", {}),
        act("read_file", {"path": "a.py"}) + "\n" + act("list_files", {}),
        "Thought: done\nFinal Answer: 42",
        act("read_file", {"path": "a.py"}) + "\nObservation: fake",
        "\n".join(act("list_files", {"path": str(i)}) for i in range(9)),
        'Thought: r\nAction: read_file\nAction Input:\n```json\n{"path": "a.py"}\n```',
    ]
    for t in texts:
        assert parse_step(t) == parse_step(t, lenient=True, first_arg=FIRST)
        assert parse_turn(t) == parse_turn(t, lenient=True, first_arg=FIRST)
    nine = "\n".join(act("list_files", {"path": str(i)}) for i in range(9))
    assert parse_turn(nine).dropped == 1
    for t in (NOISE, BENCH_FAILURE):
        assert parse_step(t) == parse_step(t, lenient=True, first_arg=FIRST)


@pytest.mark.parametrize(
    "text",
    [
        "Thought: hmm\nAction: read_file\nAction Input: oops {",
        'Action: frobnicate\nAction Input: "x"',
        "I am not sure what to do.",
    ],
)
def test_unrepairable_still_errors(text):
    s_off = parse_step(text)
    s_on = parse_step(text, lenient=True, first_arg=FIRST)
    assert s_on == s_off
    assert s_on.error == INPUT_ERROR or s_on.error == INVALID
    t_off = parse_turn(text)
    t_on = parse_turn(text, lenient=True, first_arg=FIRST)
    assert t_on == t_off
    assert t_on.error == INPUT_ERROR or t_on.error == INVALID


def test_first_required_arg():
    assert first_required_arg(ReadFileTool.parameters) == "path"
    assert first_required_arg(ListFilesTool.parameters) == "path"
    assert first_required_arg(GitStatusTool.parameters) is None
    assert first_required_arg(None) is None


def test_agent_emits_parse_repaired(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        "Thought: t\nAction: list_files\nAction Input: {'path': '.'}",
        "Final Answer: done",
    ]
    r = asyncio.run(Agent(mock_config, tmp_path, ApprovalPolicy("auto")).run("list the files"))
    events = read_events(r.log_path)
    repaired = [e for e in events if e["type"] == "parse_repaired"]
    assert len(repaired) == 1
    assert repaired[0]["repairs"] == ["single_quotes"]
    assert not [e for e in events if e["type"] == "parse_error"]


def test_agent_strict_when_disabled(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        "Thought: t\nAction: list_files\nAction Input: {'path': '.'}",
        "Final Answer: done",
    ]
    cfg = with_agent(mock_config, lenient_parse=False)
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("list the files"))
    events = read_events(r.log_path)
    assert not [e for e in events if e["type"] == "parse_repaired"]
    errors = [e for e in events if e["type"] == "parse_error"]
    assert len(errors) == 1
    assert errors[0]["error"] == INPUT_ERROR


def test_lenient_parse_config():
    models = [
        {
            "id": "mock/cheap",
            "provider": "scripted",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 2.0,
        },
        {
            "id": "mock/strong",
            "provider": "scripted",
            "tier": "strong",
            "input_usd_per_mtok": 5.0,
            "output_usd_per_mtok": 10.0,
        },
    ]
    assert (
        parse_config({"models": models, "agent": {"lenient_parse": False}}).agent.lenient_parse
        is False
    )
    assert parse_config({"models": models}).agent.lenient_parse is True
    with pytest.raises(ConfigError):
        parse_config({"models": models, "agent": {"lenient_parse": "yes"}})
