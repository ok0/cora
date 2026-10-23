from __future__ import annotations

import ast
import asyncio
import filecmp
import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import CFG_TOML, PY, act, native, tc, with_agent, with_gates_off, write_files
from cora.core import finalgate
from cora.core.agent import Agent
from cora.core.config import ConfigError, parse_config
from cora.core.react import parse_turn
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionResponse
from test_headless import base, run_cli, write_cfg

FIX = json.loads(
    (Path(__file__).parent / "fixtures" / "m16d" / "m16c_causes.json").read_text(encoding="utf-8")
)
ROOT = Path(__file__).resolve().parents[1]
TASK = "make the program"
FIX_KEYS = ("json_string_repair", "overwrite_guard")


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def _model_list() -> list[dict[str, Any]]:
    return [
        {
            "id": "mock/cheap",
            "provider": "scripted",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 2.0,
        }
    ]


@pytest.mark.parametrize("on", [False, True])
def test_json_control_chars_fixture(on):
    t = parse_turn(FIX["json_control_chars"]["reply"], lenient=True, first_arg=FA, json_strings=on)
    if not on:
        assert any(c.name == "write_file" and c.args is None for c in t.calls)
        return
    assert all(c.args is not None for c in t.calls)
    assert t.repaired[0] == "json_strings"
    write = next(c for c in t.calls if c.name == "write_file")
    assert write.args["path"] == "todo.py"
    ast.parse(write.args["content"])


@pytest.mark.parametrize("on", [False, True])
def test_json_invalid_escape_fixture(on):
    t = parse_turn(FIX["json_invalid_escape"]["reply"], lenient=True, first_arg=FA, json_strings=on)
    edit = next(c for c in t.calls if c.name == "edit_file")
    if not on:
        assert edit.args is None or t.error is not None
        return
    assert isinstance(edit.args, dict)
    assert "\\'" in edit.args["new"]


def test_json_strings_escape_rules():
    raw = "x\\d" + "\n" + "q\\\"z\\\\w\\u0041\\'" + "\t" + "e"
    reply = (
        'Thought: s\nAction: write_file\nAction Input: {"path": "a.py", "content": "' + raw + '"}'
    )
    t = parse_turn(reply, lenient=True, first_arg=FA, json_strings=True)
    assert t.calls[0].args["content"] == "x\\d\nq\"z\\wA\\'\te"


def test_json_strings_valid_reply_untouched():
    reply = act("write_file", {"path": "a.py", "content": "a\\nb"})
    on = parse_turn(reply, lenient=True, first_arg=FA, json_strings=True)
    off = parse_turn(reply, lenient=True, first_arg=FA, json_strings=False)
    assert on.repaired == ()
    assert [c.args for c in on.calls] == [c.args for c in off.calls]


def test_json_strings_truncated_not_repaired():
    reply = 'Action: write_file\nAction Input: {"path": "a.py", "content": "x\n'
    t = parse_turn(reply, lenient=True, first_arg=FA, json_strings=True)
    assert t.repaired == ()
    assert t.error is not None or any(c.args is None for c in t.calls)


def test_json_strings_agent_event(mock_config, scripted, ws):
    on_cfg = with_agent(mock_config, approval="auto", json_string_repair=True)
    scripted.script[:] = [FIX["json_control_chars"]["reply"], "Final Answer: done"]
    r = run(on_cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert (ws / "todo.py").exists()
    repaired = events(r, "parse_repaired")
    assert len(repaired) == 1
    assert "json_strings" in repaired[0]["repairs"]

    off_ws = ws / "off"
    off_ws.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [FIX["json_control_chars"]["reply"], "Final Answer: done"]
    off_cfg = with_agent(mock_config, approval="auto", json_string_repair=False)
    r_off = run(off_cfg, off_ws)
    assert not (off_ws / "todo.py").exists()
    assert events(r_off, "parse_repaired") == []


@pytest.mark.parametrize("on", [False, True])
def test_overwrite_fixture(on, mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, case["seed"])
    scripted.script[:] = [case["reply"], "Final Answer: done"]
    cfg = with_agent(mock_config, approval="auto", overwrite_guard=on)
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    target = (ws / "test_textstats.py").read_text(encoding="utf-8")
    refused = events(r, "overwrite_refused")
    if not on:
        assert target != case["seed"]["test_textstats.py"]
        assert refused == []
        return
    assert target == case["seed"]["test_textstats.py"]
    assert len(refused) == 1
    assert refused[0]["path"] == "test_textstats.py"
    assert refused[0]["mechanism"] == "overwrite_guard"
    observation = scripted.calls[1].messages[-1].content
    assert "existed before this run" in observation
    assert "def test_" in observation


def test_overwrite_once_per_run(mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, case["seed"])
    scripted.script[:] = [case["reply"], case["reply"], "Final Answer: done"]
    cfg = with_agent(mock_config, approval="auto", overwrite_guard=True)
    r = run(cfg, ws)
    assert (ws / "test_textstats.py").read_text(encoding="utf-8") != case["seed"][
        "test_textstats.py"
    ]
    assert len(events(r, "overwrite_refused")) == 1


def test_overwrite_after_read_allowed(mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, case["seed"])
    scripted.script[:] = [
        act("read_file", {"path": "test_textstats.py"}),
        case["reply"],
        "Final Answer: done",
    ]
    cfg = with_gates_off(mock_config, approval="auto", overwrite_guard=True)
    r = run(cfg, ws)
    assert (ws / "test_textstats.py").read_text(encoding="utf-8") != case["seed"][
        "test_textstats.py"
    ]
    assert events(r, "overwrite_refused") == []
    assert len(scripted.calls) == 3


@pytest.mark.parametrize("on", [False, True])
def test_overwrite_stub_template_not_delayed(on, mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, {"textstats.py": case["seed"]["textstats.py"]})
    scripted.script[:] = [
        act("write_file", {"path": "textstats.py", "content": "def f():\n    return 1\n"}),
        "Final Answer: done",
    ]
    cfg = with_gates_off(mock_config, approval="auto", overwrite_guard=on)
    r = run(cfg, ws)
    assert (ws / "textstats.py").read_text(encoding="utf-8") == "def f():\n    return 1\n"
    assert events(r, "overwrite_refused") == []
    assert len(scripted.calls) == 2


def test_overwrite_new_file_and_append_allowed(mock_config, scripted, ws):
    write_files(ws, {"p.py": "def g():\n    return 2\n"})
    scripted.script[:] = [
        act("write_file", {"path": "q.py", "content": "def h():\n    return 3\n"}),
        act("write_file", {"path": "p.py", "content": "# more\n", "append": True}),
        "Final Answer: done",
    ]
    cfg = with_agent(mock_config, approval="auto", overwrite_guard=True)
    r = run(cfg, ws)
    assert (ws / "q.py").read_text(encoding="utf-8") == "def h():\n    return 3\n"
    assert "# more" in (ws / "p.py").read_text(encoding="utf-8")
    assert events(r, "overwrite_refused") == []


def test_overwrite_multi_call_turn(mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, case["seed"])
    write_reply = act("write_file", {"path": "test_textstats.py", "content": "# x\n"})
    shell_reply = act("run_shell", {"command": f'{PY} -c "print(7)"'})
    reply = write_reply + "\n" + shell_reply[len("Thought: step\n") :]
    scripted.script[:] = [reply, "Final Answer: done"]
    cfg = with_agent(mock_config, approval="auto", overwrite_guard=True)
    r = run(cfg, ws)
    assert len(events(r, "overwrite_refused")) == 1
    assert (ws / "test_textstats.py").read_text(encoding="utf-8") == case["seed"][
        "test_textstats.py"
    ]
    shell = [e for e in events(r, "tool_call") if e["tool"] == "run_shell"]
    assert shell and shell[0]["ok"] is True


def test_overwrite_native(mock_config, scripted, ws):
    case = FIX["overwrite_spec"]
    write_files(ws, case["seed"])
    scripted.script[:] = [
        native(tc("write_file", {"path": "test_textstats.py", "content": "# x"})),
        CompletionResponse("done", 10, 5, "mock/cheap"),
    ]
    cfg = with_agent(mock_config, approval="auto", tool_protocol="native", overwrite_guard=True)
    r = run(cfg, ws)
    assert len(events(r, "overwrite_refused")) == 1
    assert (ws / "test_textstats.py").read_text(encoding="utf-8") == case["seed"][
        "test_textstats.py"
    ]


def test_protected_seed_files(tmp_path):
    write_files(tmp_path, {"stub.py": "def f():\n    raise NotImplementedError\n"})
    (tmp_path / "real.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_a():\n    assert 1 == 1\n", encoding="utf-8"
    )
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("def h():\n    return 3\n", encoding="utf-8")
    assert finalgate.protected_seed_files(tmp_path) == {"real.py", "tests/test_a.py"}


def test_fix_keys_default_true_and_invalid():
    cfg = parse_config({"models": _model_list()})
    for key in FIX_KEYS:
        assert getattr(cfg.agent, key) is True
    for key in FIX_KEYS:
        for value in ("yes", 1):
            with pytest.raises(ConfigError):
                parse_config({"models": _model_list(), "agent": {key: value}})


def test_fix_key_invalid_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + '\n[agent]\noverwrite_guard = "yes"')
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2
    assert "overwrite_guard" in result.output


@pytest.mark.parametrize("key", FIX_KEYS)
def test_toml_copies_have_fix_keys_true(key):
    paths = [ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert re.search(rf"^{key} = true", text, re.M)
    assert filecmp.cmp(paths[0], paths[1], shallow=False)


def test_no_task_specifics_m16d():
    forbidden = [
        "todo",
        "textstats",
        "text_stats",
        "rest_notes",
        "notes",
        "md_to_html",
        "sentence_count",
        "word_count",
        "char_frequency",
        "app.py",
        "inventory",
        "?!",
    ]
    core = ROOT / "src" / "cora" / "core"
    texts = [
        (core / "react.py").read_text(encoding="utf-8").lower(),
        (core / "config.py").read_text(encoding="utf-8").lower(),
        finalgate.OVERWRITE_FEEDBACK.lower(),
    ]
    for text in texts:
        for token in forbidden:
            assert token not in text


def test_m16d_fixture_sanitized():
    raw = (Path(__file__).parent / "fixtures" / "m16d" / "m16c_causes.json").read_text(
        encoding="utf-8"
    )
    patterns = [
        r"sk-or-",
        r"sk-[A-Za-z0-9]{16}",
        r"(?i)authorization",
        r"(?i)bearer ",
        r"OPENROUTER_API_KEY=",
        r"GEMINI_API_KEY=",
        r"/private/var/",
        r"/var/folders/",
        r"/Users/",
    ]
    for pattern in patterns:
        assert re.search(pattern, raw) is None, pattern
