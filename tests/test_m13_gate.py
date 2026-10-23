from __future__ import annotations

import asyncio
import json

from conftest import PY, act, with_agent, with_gates_off
from cora.core.agent import Agent
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy

PASS = f"{PY} -c \"pass\""
TEST_OK = "def test_ok():\n    assert True\n"
EDIT_TEST = act("edit_file", {"path": "tests/test_a.py", "old": "True", "new": "1"})


def write_files(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def events(r, kind=None):
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def pytest_ws(ws):
    write_files(ws, {"tests/test_ok.py": TEST_OK})
    return ws


def run_agent(cfg, ws, task="hi", on_event=None, approval="auto", **kwargs):
    return asyncio.run(
        Agent(cfg, ws, ApprovalPolicy(approval), on_event=on_event).run(task, **kwargs)
    )


def test_auto_check_runs_detected(mock_config, scripted, ws):
    pytest_ws(ws)
    cfg = with_agent(mock_config, auto_check=True)
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws)
    assert [e["command"] for e in events(r, "check")] == ["python -m pytest -q"]
    assert all(e["ok"] for e in events(r, "check"))
    assert len(events(r, "check_detected")) == 1
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_explicit_check_wins(mock_config, scripted, ws):
    pytest_ws(ws)
    cfg = with_agent(mock_config, auto_check=True)
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws, check_command=PASS)
    assert [e["command"] for e in events(r, "check")] == [PASS]
    assert not events(r, "check_detected")


def test_auto_check_off(mock_config, scripted, ws):
    pytest_ws(ws)
    cfg = with_agent(mock_config, auto_check=False)
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws)
    assert not events(r, "check")
    assert r.session.check_command is None


def test_auto_check_repl_uses_sensor_gate(mock_config, scripted, ws):
    pytest_ws(ws)
    cfg = with_agent(mock_config, auto_check=True)
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws, sensor=True)
    checks = events(r, "check")
    assert len(checks) == 1
    assert checks[0]["sensor"] is True


def test_tamper_edit_fails_gate(mock_config, scripted, ws):
    write_files(ws, {"tests/test_a.py": "def test_a():\n    assert True\n"})
    cfg = with_gates_off(mock_config, tamper_guard=True, sensor_max_retries=1)
    scripted.script[:] = [EDIT_TEST, "Final Answer: a", "Final Answer: b"]
    r = run_agent(cfg, ws, check_command=PASS, sensor=True)
    first = events(r, "check")[0]
    assert first["ok"] is False
    assert first["reason"] == "tests_modified"
    assert first["files"] == ["tests/test_a.py"]
    content = scripted.calls[2].messages[-1].content
    assert "tests_modified" in content
    assert "tests/test_a.py" in content
    assert r.stop_reason == StopReason.CHECK_FAILED


def test_tamper_delete_fails_gate(mock_config, scripted, ws):
    write_files(ws, {"tests/test_a.py": "def test_a():\n    assert True\n"})

    def hook(e):
        if e["type"] == "attempt_start":
            (ws / "tests" / "test_a.py").unlink(missing_ok=True)

    cfg = with_agent(mock_config, tamper_guard=True, max_attempts=1)
    scripted.script[:] = ["Final Answer: a"]
    r = run_agent(cfg, ws, on_event=hook, check_command=PASS)
    check = events(r, "check")[0]
    assert check["reason"] == "tests_modified"
    assert check["files"] == ["tests/test_a.py"]
    assert r.stop_reason == StopReason.CHECK_FAILED
    assert "tests_modified" in r.session.last_failure


def test_tamper_new_test_file_passes(mock_config, scripted, ws):
    write_files(ws, {"tests/test_a.py": "def test_a():\n    assert True\n"})
    cfg = with_agent(mock_config, tamper_guard=True)
    new_test = act("edit_file", {"path": "tests/test_new.py", "old": "",
                                 "new": "def test_n():\n    pass\n"})
    scripted.script[:] = [new_test, "Final Answer: ok"]
    r = run_agent(cfg, ws, check_command=PASS, sensor=True)
    checks = events(r, "check")
    assert len(checks) == 1
    assert checks[0]["ok"] is True
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_tamper_guard_off(mock_config, scripted, ws):
    write_files(ws, {"tests/test_a.py": "def test_a():\n    assert True\n"})
    cfg = with_agent(mock_config, tamper_guard=False)
    scripted.script[:] = [EDIT_TEST, "Final Answer: ok"]
    r = run_agent(cfg, ws, check_command=PASS, sensor=True)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert all("reason" not in e for e in events(r, "check"))

    def hook(e):
        if e["type"] == "attempt_start":
            (ws / "tests" / "test_a.py").unlink(missing_ok=True)

    scripted.calls.clear()
    scripted.script[:] = ["Final Answer: ok"]
    r = run_agent(cfg, ws, on_event=hook, check_command=PASS)
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert all("reason" not in e for e in events(r, "check"))


SELFTEST_EDIT = act(
    "edit_file",
    {"path": ".cora/selftest/test_self.py", "old": "", "new": "def test_x():\n    assert 1 == 2\n"},
)


def test_selftest_soft_failure(mock_config, scripted, ws):
    write_files(ws, {"a.py": "x = 1\n"})
    cfg = with_gates_off(mock_config, selftest=True)
    scripted.script[:] = [SELFTEST_EDIT, "Final Answer: done"]
    r = run_agent(cfg, ws, "x")
    assert ".cora/selftest/" in scripted.calls[0].messages[0].content
    assert (ws / ".cora" / "selftest" / "test_self.py").exists()
    selftest = events(r, "selftest")
    assert len(selftest) == 1
    assert selftest[0]["ran"] is True
    assert selftest[0]["ok"] is False
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert r.answer == "done"
    assert r.summary["selftest"]["ok"] is False
    assert "1 failed" in r.summary["selftest"]["feedback"]
    assert not events(r, "check")
    assert "self-test" in json.dumps(r.session.memory)


def test_selftest_pass(mock_config, scripted, ws):
    write_files(ws, {"a.py": "x = 1\n"})
    cfg = with_agent(mock_config, selftest=True)
    passing = act(
        "edit_file",
        {"path": ".cora/selftest/test_self.py", "old": "",
         "new": "def test_x():\n    assert 1 == 1\n"},
    )
    scripted.script[:] = [passing, "Final Answer: done"]
    r = run_agent(cfg, ws, "x")
    selftest = events(r, "selftest")
    assert len(selftest) == 1
    assert selftest[0]["ok"] is True
    assert r.stop_reason == StopReason.FINAL_ANSWER


def test_selftest_inactive_cases(mock_config, scripted, ws):
    write_files(ws, {"README.md": "# readme\n"})
    cases = [
        (with_agent(mock_config, selftest=True), {"check_command": PASS}),
        (with_agent(mock_config, selftest=False), {}),
        (with_agent(mock_config, selftest=True), {}),
    ]
    for cfg, kwargs in cases:
        scripted.calls.clear()
        scripted.script[:] = ["Final Answer: ok"]
        r = run_agent(cfg, ws, **kwargs)
        assert not any(
            ".cora/selftest" in str(m.content)
            for req in scripted.calls
            for m in req.messages
        )
        assert not events(r, "selftest")
        assert "selftest" not in r.summary


def test_selftest_dir_not_writable_when_off(mock_config, scripted, ws):
    write_files(ws, {"a.py": "x = 1\n"})
    cfg = with_agent(mock_config, selftest=False)
    scripted.script[:] = [SELFTEST_EDIT, "Final Answer: done"]
    run_agent(cfg, ws, "x", approval="policy")
    assert not (ws / ".cora" / "selftest" / "test_self.py").exists()
    assert "protected-write" in scripted.calls[1].messages[-1].content
