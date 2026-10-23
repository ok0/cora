from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
from pathlib import Path

from conftest import act
from cora.cli.io import PlainIO
from cora.cli.repl import Repl, ReplOptions
from cora.cli.ui.state import next_approval
from cora.cli.ui.statusline import statusline
from cora.core import shellguard
from cora.core.agent import Agent
from cora.core.policy import PolicyGate, PolicySettings
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy, ToolContext
from cora.core.tools.base import Workspace
from cora.core.tools.builtin import RunShellTool


def _fail(*_args, **_kwargs):
    raise AssertionError("approval prompt must not be called in policy mode")


def _fail_review(*_args, **_kwargs):
    raise AssertionError("review prompt must not be called in policy mode")


class Feed:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.out: list[str] = []

    def read(self, prompt: str) -> str:
        self.out.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    @property
    def text(self) -> str:
        return "".join(self.out)


def make(ws, cfg, *, approval="ask") -> tuple[Repl, Feed]:
    feed = Feed()
    repl = Repl(
        PlainIO(input_fn=feed.read, write=feed.out.append),
        ReplOptions(Path(ws), Path(cfg), approval=approval),
    )
    return repl, feed


def test_policy_events_and_ask_counting(mock_config, ws, scripted):
    (ws / "README.md").write_text("hello\n", encoding="utf-8")
    scripted.script[:] = [
        act("read_file", {"path": "README.md"}),
        act("web_fetch", {"url": "https://example.com"}),
        act("run_shell", {"command": "make"}),
        "Final Answer: done",
    ]
    events: list[dict] = []
    agent = Agent(mock_config, ws, ApprovalPolicy("policy", ask=_fail, review=_fail_review),
                  on_event=events.append)
    r = asyncio.run(agent.run("go"))
    decisions = [e for e in events if e["type"] == "policy_decision"]
    assert [e["rule"] for e in decisions] == ["default:read-tools", "default:web", "default"]
    assert [e["resolved"] for e in decisions] == ["allow", "deny", "deny"]
    pol = r.summary["policy"]
    assert (pol["allow"], pol["ask"], pol["deny"], pol["ask_resolved_deny"]) == (1, 1, 1, 1)
    assert len(pol["decisions"]) == 2
    for item in pol["decisions"]:
        assert {"ts", "tool", "args", "decision", "rule", "resolved"} <= set(item)
    assert len([e for e in events if e["type"] == "policy_summary"]) == 1
    dumped = json.loads(json.dumps(r.summary))
    assert {"calls", "total_cost_usd", "by_model"} <= set(dumped)


def test_cli_run_approval_policy(ws, cfg_file, monkeypatch, scripted):
    from typer.testing import CliRunner

    import cora.cli.main as main

    def boom(req):
        raise AssertionError("review must not be called")

    monkeypatch.setattr(main, "_stderr_review", boom)
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "", "new": "made\n"}),
        act("run_shell", {"command": "make"}),
        "Final Answer: done",
    ]
    result = CliRunner().invoke(main.app, ["run", "go", "-w", str(ws), "-c", str(cfg_file),
                                           "--approval", "policy"])
    assert result.exit_code == 0, result.output
    assert (ws / "a.txt").exists()
    assert "approval: policy" in result.output
    assert "policy: mode=policy" in result.output
    assert "[policy] deny run_shell (default)" in result.output


def test_repl_approval_policy_command(ws, cfg_file):
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/approval")
    assert "options: ask, auto, deny, policy" in feed.text
    repl.dispatch("/approval policy")
    assert repl.policy.mode == "policy"
    assert "approval:policy" in statusline(repl.ui, 120)
    assert "not an OS sandbox" in feed.text
    msg = repl.cycle_approval()
    assert "ask" in msg
    assert repl.policy.mode == "ask"


def test_shift_tab_never_enters_policy():
    mode = "ask"
    for _ in range(6):
        mode = next_approval(mode)
        assert mode != "policy"
    assert next_approval("policy") == "ask"


def test_repl_policy_never_prompts(ws, cfg_file, monkeypatch, scripted):
    def boom(self, req):
        raise AssertionError("the REPL must never prompt in policy mode")

    monkeypatch.setattr(Repl, "_review", boom)
    (ws / "a.txt").write_text("MARKER\n", encoding="utf-8")
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "MARKER", "new": "EDITED"}),
        act("web_fetch", {"url": "https://example.com"}),
        act("run_shell", {"command": "make"}),
        "Final Answer: done",
    ]
    repl, feed = make(ws, cfg_file, approval="policy")
    repl.submit("go")
    assert "EDITED" in (ws / "a.txt").read_text(encoding="utf-8")
    assert "denied by policy" in feed.text


def test_sensor_check_is_confined_in_policy_mode(mock_config, ws, monkeypatch, scripted):
    def boom(self, *args, **kwargs):
        raise AssertionError("the check command must not run")

    monkeypatch.setattr(RunShellTool, "run", boom)
    scripted.script[:] = ["Final Answer: done"]
    events: list[dict] = []
    agent = Agent(mock_config, ws, ApprovalPolicy("policy"), on_event=events.append)
    r = asyncio.run(agent.run("x", check_command="cat ../secret.txt", sensor=True))
    assert r.stop_reason == StopReason.CHECK_FAILED
    check = [e for e in events if e["type"] == "check"][-1]
    assert check["policy"] == "floor:outside-workspace"


def test_sensor_check_confined_with_shell_confinement(mock_config, ws, monkeypatch, scripted):
    def boom(self, *args, **kwargs):
        raise AssertionError("the check command must not run")

    monkeypatch.setattr(RunShellTool, "run", boom)
    scripted.script[:] = ["Final Answer: done"]
    cfg = dataclasses.replace(mock_config, policy=PolicySettings(shell_confinement=True))
    events: list[dict] = []
    agent = Agent(cfg, ws, ApprovalPolicy("auto"), on_event=events.append)
    r = asyncio.run(agent.run("x", check_command="cat ../secret.txt", sensor=True))
    assert r.stop_reason == StopReason.CHECK_FAILED
    check = [e for e in events if e["type"] == "check"][-1]
    assert check["policy"] == "floor:outside-workspace"


def test_policy_shell_env_is_clean(ws, monkeypatch):
    for name, value in {"OPENROUTER_API_KEY": "sk-1", "FOO_API_KEY": "sk-2",
                        "GITHUB_TOKEN": "gh", "MY_SECRET": "s", "PLAIN_VAR": "plain"}.items():
        monkeypatch.setenv(name, value)
    hidden = frozenset({"OPENROUTER_API_KEY"})
    gate = PolicyGate(PolicySettings(), ws, hidden_env=hidden)
    ctx = ToolContext(Workspace(ws), ApprovalPolicy("policy"), 10, hidden_env=hidden, gate=gate)
    out = asyncio.run(RunShellTool().run({"command": "env; pwd"}, ctx)).output
    for name in ("OPENROUTER_API_KEY", "FOO_API_KEY", "GITHUB_TOKEN", "MY_SECRET"):
        assert f"{name}=" not in out
    assert f"HOME={ws.resolve() / '.cora' / 'home'}" in out
    assert out.strip().splitlines()[-1] == str(ws.resolve())

    ctx_auto = ToolContext(Workspace(ws), ApprovalPolicy("auto"), 10, hidden_env=hidden,
                           gate=gate)
    out_auto = asyncio.run(RunShellTool().run({"command": "env"}, ctx_auto)).output
    assert "FOO_API_KEY=" in out_auto
    assert "PLAIN_VAR=" in out_auto
    assert "OPENROUTER_API_KEY=" not in out_auto


def test_strict_profile_env_clean(ws):
    env = PolicyGate(PolicySettings(), ws, strict=True).shell_env("auto")
    assert not any(shellguard.secret_like(k) for k in env)
    assert env["HOME"].endswith(".cora/home")


def test_sandbox_off_by_default(ws):
    gate = PolicyGate(PolicySettings(), ws)
    assert gate.sandbox_argv("ls", "ask") is None
    assert gate.warnings == []


def test_sandbox_unavailable_warns(mock_config, ws, monkeypatch, scripted):
    monkeypatch.setattr(shellguard, "sandbox_available", lambda: False)
    gate = PolicyGate(PolicySettings(sandbox=True), ws)
    assert "sandbox-exec" in gate.warnings[0]
    assert gate.sandbox_argv("ls", "policy") is None
    scripted.script[:] = ["Final Answer: done"]
    cfg = dataclasses.replace(mock_config, policy=PolicySettings(sandbox=True))
    events: list[dict] = []
    asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto"), on_event=events.append).run("x"))
    assert any(e["type"] == "policy_warning" for e in events)


def test_sandbox_available_wraps(ws, monkeypatch):
    monkeypatch.setattr(shellguard, "sandbox_available", lambda: True)
    gate = PolicyGate(PolicySettings(sandbox=True), ws)
    argv = gate.sandbox_argv("ls", "policy")
    assert argv[:2] == ["sandbox-exec", "-p"]
    assert argv[-1] == "ls"
    assert "(version 1)" in argv[2]
    assert gate.sandbox_argv("ls", "ask") is None


def test_strict_autoenables_sandbox_when_available(ws, monkeypatch):
    monkeypatch.setattr(shellguard, "sandbox_available", lambda: True)
    gate = PolicyGate(PolicySettings(sandbox=False), ws, strict=True)
    assert gate.sandbox is True
    assert gate.sandbox_argv("ls", "policy")[:2] == ["sandbox-exec", "-p"]


def test_strict_warns_when_sandbox_unavailable_on_darwin(ws, monkeypatch):
    monkeypatch.setattr(shellguard, "sandbox_available", lambda: False)
    monkeypatch.setattr(sys, "platform", "darwin")
    gate = PolicyGate(PolicySettings(), ws, strict=True)
    assert gate.sandbox is False
    assert any("strict" in w for w in gate.warnings)
