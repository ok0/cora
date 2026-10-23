from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

from conftest import CFG_TOML, ScriptedProvider, act, with_agent, with_gates_off
from cora.core.agent import Agent
from cora.core.config import parse_config
from cora.core.prompts import REPEAT_WHAT
from cora.core.repeat import RepeatTracker
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from record_util import entries, record_env, seed_ws

FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))
TASK = "make the program"


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def cfg_on(mock_config, **keys):
    return with_gates_off(mock_config, approval="auto", json_string_repair=True, **keys)


def feedback(messages) -> list[str]:
    return [m.content for m in messages if "Repetition detected" in m.content]


def _blocked_init(self, settings) -> None:
    raise AssertionError("provider constructed in replay")


def test_tracker_same_reply():
    tr = RepeatTracker()
    assert tr.observe("a  b\n", None) is None
    s2 = tr.observe(" a b", None)
    assert (s2.kind, s2.count, s2.feedback, s2.boost) == ("same_reply", 2, True, False)
    s3 = tr.observe("a b", None)
    assert (s3.kind, s3.count, s3.feedback, s3.boost) == ("same_reply", 3, False, True)
    s4 = tr.observe("a b", None)
    assert (s4.kind, s4.count, s4.feedback, s4.boost) == ("same_reply", 4, False, True)


def test_tracker_failure_kinds():
    tr = RepeatTracker()
    pe = ("parse_error", None)
    em = ("edit_mismatch", "x")
    assert tr.observe("p1", pe) is None
    s = tr.observe("p2", pe)
    assert (s.kind, s.count) == ("parse_error", 2)
    assert tr.observe("q", em) is None
    s = tr.observe("r", em)
    assert (s.kind, s.count) == ("edit_mismatch", 2)
    assert tr.observe("s", ("edit_mismatch", "y")) is None


def test_tracker_success_resets():
    tr = RepeatTracker()
    assert tr.observe("a", ("parse_error", None)) is None
    assert tr.observe("b", None) is None
    assert tr.observe("c", ("parse_error", None)) is None


def test_repeat_parse_error_fixture(mock_config, scripted, ws):
    a = FIX["write_escape"]["reply"]
    scripted.script[:] = [a, a, a, a, "Final Answer: done"]
    r = run(cfg_on(mock_config, repeat_breaker=True), ws)
    assert [c.temperature for c in scripted.calls] == [0.0, 0.0, 0.0, 0.7, 0.7]
    rep = [(e["iteration"], e["kind"], e["count"]) for e in events(r, "repeat_detected")]
    assert rep == [(2, "parse_error", 2), (3, "parse_error", 3), (4, "parse_error", 4)]
    assert len(feedback(scripted.calls[-1].messages)) == 1
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_repeat_boost_returns_to_base(mock_config, scripted, ws):
    a = FIX["write_escape"]["reply"]
    (ws / "f.txt").write_text("hi\n", encoding="utf-8")
    scripted.script[:] = [a, a, a, act("read_file", {"path": "f.txt"}), "Final Answer: done"]
    run(cfg_on(mock_config, repeat_breaker=True), ws)
    assert [c.temperature for c in scripted.calls] == [0.0, 0.0, 0.0, 0.7, 0.0]


def test_repeat_edit_mismatch_fixture(mock_config, scripted, ws):
    (ws / "md2html.py").write_text(FIX["edit_backslash"]["file"], encoding="utf-8")
    b = FIX["edit_backslash"]["reply"]
    scripted.script[:] = [b, b, b, "Final Answer: done"]
    r = run(cfg_on(mock_config, repeat_breaker=True), ws)
    rep = [(e["kind"], e["count"]) for e in events(r, "repeat_detected")]
    assert rep == [("edit_mismatch", 2), ("edit_mismatch", 3)]
    assert [c.temperature for c in scripted.calls] == [0.0, 0.0, 0.0, 0.7]
    assert any(REPEAT_WHAT["edit_mismatch"] in m.content for m in scripted.calls[-1].messages)


def test_repeat_same_reply_success(mock_config, scripted, ws):
    (ws / "f.txt").write_text("hi\n", encoding="utf-8")
    read = act("read_file", {"path": "f.txt"})
    scripted.script[:] = [read, read, read, "Final Answer: done"]
    r = run(cfg_on(mock_config, repeat_breaker=True), ws)
    kinds = [e["kind"] for e in events(r, "repeat_detected")]
    assert kinds and set(kinds) == {"same_reply"}


def test_repeat_feedback_raw_alt(mock_config, scripted, ws, tmp_path):
    a = FIX["write_escape"]["reply"]
    scripted.script[:] = [a, a, "Final Answer: done"]
    run(cfg_on(mock_config, repeat_breaker=True, raw_file_body=True), ws)
    fb = feedback(scripted.calls[-1].messages)
    assert len(fb) == 1 and "<<<CONTENT" in fb[0]

    ws2 = tmp_path / "ws2"
    ws2.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [a, a, "Final Answer: done"]
    run(cfg_on(mock_config, repeat_breaker=True), ws2)
    fb = feedback(scripted.calls[-1].messages)
    assert len(fb) == 1 and "<<<CONTENT" not in fb[0]


def test_repeat_off_no_effect(mock_config, scripted, ws):
    a = FIX["write_escape"]["reply"]
    scripted.script[:] = [a, a, a, "Final Answer: done"]
    r = run(cfg_on(mock_config), ws)
    assert events(r, "repeat_detected") == []
    assert all(c.temperature == 0.0 for c in scripted.calls)
    assert not any(feedback(c.messages) for c in scripted.calls)


def test_repeat_does_not_change_limits(mock_config, scripted, tmp_path):
    a = FIX["write_escape"]["reply"]
    results = {}
    for on in (False, True):
        scripted.calls.clear()
        scripted.script[:] = [a] * 5
        cfg = with_agent(
            cfg_on(mock_config, repeat_breaker=on), max_iterations=3
        )
        ws = tmp_path / f"ws_{on}"
        ws.mkdir()
        r = run(cfg, ws)
        results[on] = (r.stop_reason, len(scripted.calls), r)
    assert results[False][0] == results[True][0]
    assert results[False][1] == results[True][1]
    on_types = [e["type"] for e in events(results[True][2])]
    assert not [t for t in on_types if t.startswith(("tripwire", "escalat"))]


def test_repeat_record_replay_roundtrip(scripted, tmp_path, monkeypatch, no_network):
    rec = tmp_path / "rec"
    cfg = with_gates_off(
        parse_config(tomllib.loads(CFG_TOML)), approval="auto", repeat_breaker=True
    )
    a = FIX["write_escape"]["reply"]
    scripted.script[:] = [a, a, a, "Final Answer: done"]
    ws_a = seed_ws(tmp_path / "a")
    monkeypatch.setenv("HOME", str(tmp_path / "home1"))
    record_env(monkeypatch, "record", rec)
    rec_run = asyncio.run(Agent(cfg, ws_a, ApprovalPolicy("auto")).run("q"))
    temps = [
        json.loads(p.read_text(encoding="utf-8"))["request"]["temperature"]
        for p in entries(rec)
    ]
    assert temps.count(0.7) == 1

    monkeypatch.setenv("HOME", str(tmp_path / "home2"))
    record_env(monkeypatch, "replay", rec)
    monkeypatch.setattr(ScriptedProvider, "__init__", _blocked_init)
    ws_b = seed_ws(tmp_path / "b")
    rep_run = asyncio.run(Agent(cfg, ws_b, ApprovalPolicy("auto")).run("q"))
    assert rep_run.answer == rec_run.answer
    assert rep_run.stop_reason == rec_run.stop_reason

    def key(e):
        return (e["iteration"], e["kind"], e["count"])

    assert [key(e) for e in events(rep_run, "repeat_detected")] == [
        key(e) for e in events(rec_run, "repeat_detected")
    ]
