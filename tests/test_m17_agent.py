from __future__ import annotations

import asyncio
import inspect
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import cora.core.memory as memory_mod
from conftest import act, with_gates_off
from cora.core.agent import Agent
from cora.core.config import CoraConfig, parse_config
from cora.core.memory import (
    LEDGER_HEADER,
    OMITTED_MARKER,
    SUMMARY_INPUT_CHARS,
    SUMMARY_SYSTEM,
    PersistentStore,
)
from cora.core.observability import read_events
from cora.core.state import SessionStore
from cora.core.tools import ApprovalPolicy
from cora.core.types import messages_tokens
from test_m17_off_identity import PY_ALIAS, link_python

REPO = Path(__file__).resolve().parents[1]
SECRET = "sk-test-dummy-123456"


def _cfg(**mem) -> CoraConfig:
    base = parse_config(
        {
            "models": [
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
            ],
            "agent": {"approval": "auto", "max_iterations": 80},
            "memory": {
                "context_budget_tokens": 4000,
                "keep_last_messages": 4,
                "max_observation_chars": 4000,
                **mem,
            },
        }
    )
    return with_gates_off(base)


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "big.txt").write_text(
        "\n".join(f"line {i} " + "x" * 60 for i in range(5000)) + "\n",
        encoding="utf-8",
    )
    link_python(ws)
    return ws


def _long() -> list:
    return [
        act("write_file", {"path": "a.py", "content": "x = 1\n"}),
        act("edit_file", {"path": "a.py", "old": "x = 1", "new": "x = 2"}),
        act("run_shell", {"command": f"{PY_ALIAS} -c \"print('boom'); raise SystemExit(1)\""}),
        "garbage without action",
        *[act("read_file", {"path": "big.txt", "start_line": 1 + 50 * i}) for i in range(60)],
        "Final Answer: done",
    ]


def _run(
    scripted, cfg: CoraConfig, ws: Path, script: list, task: str = "run the listed steps in order"
):
    scripted.script[:] = script
    agent = Agent(cfg, ws, ApprovalPolicy("auto"))
    r = asyncio.run(agent.run(task))
    return agent, r


def _ledger_msgs(req) -> list[str]:
    return [m.content for m in req.messages if m.content.startswith(LEDGER_HEADER)]


def _llm(events: list[dict], purpose: str | None = None) -> list[dict]:
    return [
        e for e in events
        if e["type"] == "llm_call" and (purpose is None or e.get("purpose") == purpose)
    ]


def test_long_run_ledger_on_keeps_state(scripted, tmp_path):
    ws = _ws(tmp_path)
    _, r = _run(scripted, _cfg(ledger=True), ws, _long())
    for req in scripted.calls:
        assert messages_tokens(req.messages) <= 4000
    msgs = _ledger_msgs(scripted.calls[-1])
    assert len(msgs) == 1
    text = msgs[0]
    for needle in ("a.py", "FAIL", "SystemExit(1)", "parse_error"):
        assert needle in text
    evicted = PersistentStore(ws / ".cora" / "memory").read(r.session.id, "evicted")
    assert len(evicted) > 10
    events = read_events(r.log_path)
    assert [e for e in _llm(events) if e.get("purpose") != "react"] == []


def test_long_run_ledger_off_loses_state(scripted, tmp_path):
    ws = _ws(tmp_path)
    _run(scripted, _cfg(), ws, _long())
    last = scripted.calls[-1]
    assert not _ledger_msgs(last)
    assert all("a.py" not in m.content for m in last.messages)
    assert any(
        OMITTED_MARKER in m.content for req in scripted.calls for m in req.messages
    )


def test_ledger_events(scripted, tmp_path):
    ws = _ws(tmp_path)
    _, r = _run(scripted, _cfg(ledger=True), ws, _long())
    events = read_events(r.log_path)
    assert any(e["type"] == "ledger_update" for e in events)
    assert any(e["type"] == "ledger_evict_note" for e in events)
    assert not any(e["type"] == "summary_call" for e in events)


def test_resume_keeps_ledger(scripted, tmp_path):
    ws = _ws(tmp_path)
    _, r = _run(scripted, _cfg(ledger=True), ws, _long())
    loaded = SessionStore(ws / ".cora" / "sessions").load(r.session.id)
    assert "a.py" in loaded.memory["ledger"]["files"]


def test_summarize_calls_equal_evictions(scripted, tmp_path):
    ws = _ws(tmp_path)
    main = iter(_long())

    def dispatch(req):
        if req.messages[0].content == SUMMARY_SYSTEM:
            return "S: earlier steps summarized."
        return next(main, "Final Answer: done")

    agent, r = _run(scripted, _cfg(ledger=True, summarize="llm"), ws, [dispatch] * 400)
    events = read_events(r.log_path)
    summaries = _llm(events, "summary")
    evicts = [e for e in events if e["type"] == "ledger_evict_note"]
    assert len(evicts) >= 1
    assert len(summaries) == len(evicts)
    summary_reqs = [req for req in scripted.calls if req.messages[0].content == SUMMARY_SYSTEM]
    assert len(summary_reqs) == len(summaries)
    for req in summary_reqs:
        user = req.messages[1].content
        assert len(user) <= SUMMARY_INPUT_CHARS
        assert "line 1 " not in user
    assert "Earlier steps: S: earlier steps summarized." in _ledger_msgs(scripted.calls[-1])[0]
    assert sum(e["cost_usd"] for e in summaries) > 0
    assert agent.governor.usage().cost_usd == pytest.approx(
        sum(e["cost_usd"] or 0.0 for e in _llm(events))
    )


def test_summarize_no_eviction_no_call(scripted, tmp_path):
    ws = _ws(tmp_path)
    script = [
        act("read_file", {"path": "big.txt", "start_line": 1}),
        act("read_file", {"path": "big.txt", "start_line": 51}),
        "Final Answer: done",
    ]
    _, r = _run(scripted, _cfg(ledger=True, summarize="llm"), ws, script)
    events = read_events(r.log_path)
    assert _llm(events, "summary") == []
    assert not any(e["type"] == "summary_call" for e in events)


def test_summarize_failure_falls_back(scripted, tmp_path):
    ws = _ws(tmp_path)
    main = iter(_long())

    def dispatch(req):
        if req.messages[0].content == SUMMARY_SYSTEM:
            raise RuntimeError("down")
        return next(main, "Final Answer: done")

    _, r = _run(scripted, _cfg(ledger=True, summarize="llm"), ws, [dispatch] * 400)
    assert r.answer == "done"
    events = read_events(r.log_path)
    failed = [e for e in events if e["type"] == "summary_call"]
    assert any(e.get("ok") is False and e.get("error") == "RuntimeError" for e in failed)
    text = _ledger_msgs(scripted.calls[-1])[0]
    assert "a.py" in text
    assert "Earlier steps:" not in text


def test_summarize_llm_without_ledger(scripted, tmp_path):
    ws = _ws(tmp_path)
    main = iter(_long())

    def dispatch(req):
        if req.messages[0].content == SUMMARY_SYSTEM:
            return "S: earlier steps summarized."
        return next(main, "Final Answer: done")

    _run(scripted, _cfg(ledger=False, summarize="llm"), ws, [dispatch] * 400)
    msgs = _ledger_msgs(scripted.calls[-1])
    assert len(msgs) == 1
    body = [line for line in msgs[0].splitlines()[1:] if line]
    assert body
    assert all(line.startswith("Earlier steps:") for line in body)
    assert "Files changed" not in msgs[0]


def test_protected_and_secret_masked(scripted, tmp_path, monkeypatch):
    monkeypatch.setenv("CORA_TEST_API_KEY", SECRET)
    ws = _ws(tmp_path)
    script = [
        act("run_shell", {"command": f"{PY_ALIAS} -c \"print('{SECRET}'); raise SystemExit(1)\""}),
        "Final Answer: done",
    ]
    _, r = _run(scripted, _cfg(ledger=True), ws, script)
    loaded = SessionStore(ws / ".cora" / "sessions").load(r.session.id)
    dumped = json.dumps(loaded.memory["ledger"], ensure_ascii=False)
    assert SECRET not in dumped
    assert "<redacted>" in dumped
    for req in scripted.calls:
        for text in _ledger_msgs(req):
            assert SECRET not in text
            assert "<redacted>" in text


def test_non_sensor_check_recorded_in_ledger(scripted, tmp_path):
    check = f"{PY_ALIAS} -c \"print('ok')\""
    scripted.script[:] = ["Final Answer: done"]
    store_on = tmp_path / "on"
    store_on.mkdir()
    link_python(store_on)
    r_on = asyncio.run(
        Agent(_cfg(ledger=True), store_on, ApprovalPolicy("auto")).run(
            "run the check", check_command=check
        )
    )
    loaded_on = SessionStore(store_on / ".cora" / "sessions").load(r_on.session.id)
    checks = loaded_on.memory["ledger"]["checks"]
    assert any("print('ok')" in c["command"] and c["ok"] is True for c in checks)

    store_off = tmp_path / "off"
    store_off.mkdir()
    link_python(store_off)
    scripted.script[:] = ["Final Answer: done"]
    r_off = asyncio.run(
        Agent(_cfg(ledger=False), store_off, ApprovalPolicy("auto")).run(
            "run the check", check_command=check
        )
    )
    loaded_off = SessionStore(store_off / ".cora" / "sessions").load(r_off.session.id)
    assert not loaded_off.memory.get("ledger")
    assert r_off.answer == "done"
    assert any(e["type"] == "check" for e in read_events(r_off.log_path))


def test_no_task_names_in_ledger_code():
    source = inspect.getsource(memory_mod)
    for name in (
        "e2e_text_stats",
        "e2e_refactor_inventory",
        "query_client_timeout",
        "query_env_override",
    ):
        assert name not in source


M17_BASE = "9eee79f"  # M16d tip, parent of the first M17 commit
M17_TIP = "310a282"  # last M17 commit (docs: document ledger keys and events)


def test_bench_untouched():
    """M17 R10/AC8: the M17 commits make no change under src/cora/bench.

    Pinned to the M17 commit range so later milestones that legitimately
    edit bench (e.g. M18b R5) do not invalidate the guard.
    """
    if shutil.which("git") is None:
        pytest.skip("git is unavailable")
    for rev in (M17_BASE, M17_TIP):
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{rev}^{{commit}}"],
            cwd=REPO,
            capture_output=True,
        )
        if probe.returncode != 0:
            pytest.skip(f"history for {rev} unavailable (shallow clone?)")
    result = subprocess.run(
        ["git", "diff", "--quiet", M17_BASE, M17_TIP, "--", "src/cora/bench"],
        cwd=REPO,
    )
    assert result.returncode == 0
