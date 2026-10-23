from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

from conftest import PY, act, with_agent, with_gates_off, write_files
from cora.core import finalgate
from cora.core.agent import Agent
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy

CAUSES_PATH = Path(__file__).parent / "fixtures" / "m16c" / "m16_causes.json"
CORE_DIR = Path(__file__).resolve().parents[1] / "src" / "cora" / "core"
KEYS = ["verify_before_final", "compile_check", "edge_case_prompt", "stub_check"]
TASK = "make the program"

PREFIX = {
    "verify_before_final": [act("write_file", {"path": "m.py", "content": "x = 1\n"})],
    "compile_check": [act("write_file", {"path": "m.py", "content": "def f(:\n    pass\n"})],
    "edge_case_prompt": [
        act("write_file", {"path": "m.py", "content": "def f():\n    return 1\n"})
    ],
    "stub_check": [act("write_file", {"path": "m.py", "content": "def f():\n    pass\n"})],
}


def _subst(value: Any, ws: Path | None) -> Any:
    if isinstance(value, str):
        out = value.replace("<PY>", PY)
        if ws is not None:
            out = out.replace("<ws>", str(ws))
        return out
    if isinstance(value, list):
        return [_subst(v, ws) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, ws) for k, v in value.items()}
    return value


def load_case(key: str, ws: Path | None = None) -> dict:
    raw = json.loads(CAUSES_PATH.read_text(encoding="utf-8"))
    return _subst(raw[key], ws)


def seed_ws(ws: Path, case: dict) -> None:
    write_files(ws, case["seed"])


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def gate_finals(r, key: str | None = None) -> list[dict]:
    return [
        e
        for e in events(r, "gate_feedback")
        if e["stage"] == "final" and (key is None or e["mechanism"] == key)
    ]


def _all_on(**extra: Any) -> dict[str, bool]:
    return {k: True for k in KEYS} | extra


@pytest.mark.parametrize("key", KEYS)
def test_fixture_reproduces_cause(key, mock_config, scripted, ws):
    case = load_case(key, ws)
    seed_ws(ws, case)
    before = finalgate.defs_snapshot(ws)

    scripted.script[:] = list(case["replies"])
    off_cfg = with_gates_off(mock_config, approval="auto", max_iterations=40)
    r_off = run(off_cfg, ws)
    assert r_off.stop_reason == StopReason.FINAL_ANSWER
    assert events(r_off, "gate_feedback") == []

    tool_calls = events(r_off, "tool_call")
    if key == "compile_check":
        assert finalgate.syntax_errors(ws, ["app.py"])
    elif key == "stub_check":
        assert finalgate.stub_findings(ws, before, ["textstats.py"])
    elif key == "verify_before_final":
        writes = [i for i, e in enumerate(tool_calls) if e["tool"] in ("write_file", "edit_file")]
        last_write = writes[-1]
        assert not any(
            e["tool"] == "run_shell" and e.get("ok") for e in tool_calls[last_write + 1 :]
        )
    else:
        assert not any(e["tool"] == "run_shell" for e in tool_calls)

    ws_on = ws / "on"
    ws_on.mkdir()
    seed_ws(ws_on, case)
    scripted.calls.clear()
    scripted.script[:] = list(case["replies"]) + ["Final Answer: done"]
    on_cfg = with_gates_off(mock_config, approval="auto", max_iterations=40, **{key: True})
    r_on = run(on_cfg, ws_on)
    assert r_on.stop_reason == StopReason.FINAL_ANSWER
    finals = gate_finals(r_on, key)
    assert len(finals) == 1
    assert len(gate_finals(r_on)) == 1
    assert len(scripted.calls) == len(case["replies"]) + 1
    last = [m.content for m in scripted.calls[-1].messages]
    assert any("Not accepted yet" in c for c in last)
    if key == "compile_check":
        assert any(re.search(r"app\.py:\d+:", c) for c in last)
        assert any(e["stage"] == "edit" for e in events(r_on, "gate_feedback"))
        earlier = [m.content for call in scripted.calls[:-1] for m in call.messages]
        assert any("Syntax check:" in c for c in earlier)
    if key == "stub_check":
        assert any(re.search(r"textstats\.py:\d+:", c) for c in last)


def test_verify_refuses_once_then_accepts(mock_config, scripted, ws):
    scripted.script[:] = [
        act("write_file", {"path": "m.py", "content": "x = 1\n"}),
        "Final Answer: a",
        "Final Answer: b",
    ]
    cfg = with_gates_off(mock_config, approval="auto", verify_before_final=True)
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "b"
    assert len(scripted.calls) == 3
    assert len(events(r, "gate_feedback")) == 1


def test_verify_accepts_after_passing_check(mock_config, scripted, ws):
    scripted.script[:] = [
        act("write_file", {"path": "m.py", "content": "x = 1\n"}),
        act("run_shell", {"command": f'{PY} -c "pass"'}),
        "Final Answer: a",
    ]
    cfg = with_gates_off(mock_config, approval="auto", verify_before_final=True)
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "a"
    assert len(scripted.calls) == 3
    assert events(r, "gate_feedback") == []


def test_verify_ignores_failed_and_readonly_commands(mock_config, scripted, ws):
    scripted.script[:] = [
        act("write_file", {"path": "m.py", "content": "x = 1\n"}),
        act("run_shell", {"command": "ls"}),
        act("run_shell", {"command": f'{PY} -c "import sys; sys.exit(1)"'}),
        "Final Answer: a",
        "Final Answer: done",
    ]
    cfg = with_agent(mock_config, approval="auto", verify_before_final=True)
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "done"
    assert len(scripted.calls) == 5
    assert len(gate_finals(r, "verify_before_final")) == 1


def test_no_edit_no_refusal_all_keys_on(mock_config, scripted, ws):
    scripted.script[:] = ["Final Answer: a"]
    cfg = with_agent(mock_config, approval="auto", **_all_on())
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "a"
    assert len(scripted.calls) == 1
    assert events(r, "gate_feedback") == []


@pytest.mark.parametrize("key", KEYS)
def test_each_mechanism_at_most_once_per_run(key, mock_config, scripted, ws):
    scripted.script[:] = PREFIX[key] + [
        "Final Answer: a",
        "Final Answer: b",
        "Final Answer: c",
    ]
    cfg = with_agent(mock_config, approval="auto", max_iterations=40, **{key: True})
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "b"
    assert len(gate_finals(r, key)) == 1
    assert len(scripted.calls) == len(PREFIX[key]) + 2


def test_all_keys_combined_single_refusal(mock_config, scripted, ws):
    scripted.script[:] = [
        act("write_file", {"path": "a.py", "content": "def f(:\n"}),
        act("write_file", {"path": "m.py", "content": "def g():\n    pass\n"}),
        "Final Answer: a",
        "Final Answer: done",
    ]
    cfg = with_agent(mock_config, approval="auto", max_iterations=40, **_all_on())
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "done"
    assert len(scripted.calls) == 4
    finals = gate_finals(r)
    assert {e["mechanism"] for e in finals} == set(KEYS)
    assert len(finals) == len(KEYS)


def test_gate_skipped_at_iteration_cap(mock_config, scripted, ws):
    scripted.script[:] = [
        act("write_file", {"path": "m.py", "content": "x = 1\n"}),
        "Final Answer: a",
    ]
    cfg = with_gates_off(mock_config, approval="auto", max_iterations=2, verify_before_final=True)
    r = run(cfg, ws)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "a"
    assert events(r, "gate_feedback") == []


def test_is_check_command():
    assert finalgate.is_check_command("ls -la") is False
    assert finalgate.is_check_command("FOO=1 pytest -q") is True
    assert finalgate.is_check_command("") is False


def test_syntax_errors_reports_line(tmp_path):
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    errs = finalgate.syntax_errors(tmp_path, ["bad.py"])
    assert any(e.startswith("bad.py:1:") for e in errs)


def test_stub_findings_detects_and_skips(tmp_path):
    (tmp_path / "s.py").write_text(
        "def a():\n"
        "    pass\n"
        "def b():\n"
        "    ...\n"
        "def c():\n"
        "    raise NotImplementedError\n"
        "def d():\n"
        "    raise NotImplementedError()\n"
        "from abc import abstractmethod\n"
        "from typing import Protocol\n"
        "class K:\n"
        "    @abstractmethod\n"
        "    def n(self):\n"
        "        pass\n"
        "class P(Protocol):\n"
        "    def m(self):\n"
        "        pass\n"
        "def ok():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    findings = finalgate.stub_findings(tmp_path, {}, [])
    text = "\n".join(findings)
    for name in ("a", "b", "c", "d"):
        assert f" {name} is a stub" in text
    for name in ("n", "m", "ok"):
        assert f" {name} is a stub" not in text


def test_stub_findings_reports_removed_definition(tmp_path):
    path = tmp_path / "s.py"
    path.write_text("def keep():\n    return 1\n\ndef gone():\n    return 2\n", encoding="utf-8")
    baseline = finalgate.defs_snapshot(tmp_path)
    path.write_text("def keep():\n    return 1\n", encoding="utf-8")
    findings = finalgate.stub_findings(tmp_path, baseline, ["s.py"])
    assert any("gone was defined before your edits and is now missing" in f for f in findings)


def test_no_task_specifics_in_core():
    """Checks finalgate.py in full (it holds the four feedback texts).

    agent.py is checked with the pre-existing `plan-todo` mode name removed,
    since that string predates M16c and is not task-specific.
    """
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
    gate_text = (CORE_DIR / "finalgate.py").read_text(encoding="utf-8").lower()
    agent_text = (CORE_DIR / "agent.py").read_text(encoding="utf-8").lower()
    agent_text = agent_text.replace("plan-todo", "")
    for text in (gate_text, agent_text):
        for token in forbidden:
            assert token not in text


def test_fixtures_sanitized():
    raw = CAUSES_PATH.read_text(encoding="utf-8")
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
