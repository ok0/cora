from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CFG_TOML, act
from cora.cli.io import PlainIO
from cora.cli.repl import Repl, ReplOptions
from cora.core.errors import ProviderError


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


def make(ws, cfg, *, delegate=False) -> tuple[Repl, Feed]:
    feed = Feed()
    repl = Repl(
        PlainIO(input_fn=feed.read, write=feed.out.append),
        ReplOptions(Path(ws), Path(cfg), approval="auto", delegate=delegate),
    )
    return repl, feed


def _boom(req):
    raise ProviderError("boom")


def test_delegate_show_on_off_invalid(scripted, ws, cfg_file):
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/delegate")
    assert "delegation: off (source: default)" in feed.text
    repl.dispatch("/delegate on")
    assert repl.cfg.delegation.enabled is True
    assert "for this session" in feed.text
    repl.dispatch("/delegate off")
    assert repl.cfg.delegation.enabled is False
    before = repl.snapshot()
    repl.dispatch("/delegate maybe")
    repl.dispatch("/delegate on off")
    assert "error: usage: /delegate [on|off]" in feed.text
    assert repl.snapshot() == before


@pytest.mark.parametrize(
    "enabled,flag,command,expected,source",
    [
        (False, False, None, "off", "default"),
        (True, False, None, "on", "config"),
        (False, True, None, "on", "--delegate"),
        (True, False, "off", "off", "/delegate"),
        (False, True, "off", "off", "/delegate"),
        (False, False, "on", "on", "/delegate"),
    ],
)
def test_delegate_priority(scripted, ws, tmp_path, enabled, flag, command, expected, source):
    path = tmp_path / "cora.toml"
    text = CFG_TOML + ("\n[delegation]\nenabled = true\n" if enabled else "")
    path.write_text(text, encoding="utf-8")
    repl, feed = make(ws, path, delegate=flag)
    if command:
        repl.dispatch(f"/delegate {command}")
    repl.dispatch("/delegate")
    assert f"delegation: {expected} (source: {source})" in feed.text


def test_delegate_on_runs_subagent(scripted, ws, cfg_file):
    scripted.script[:] = [
        act("delegate", {"task": "t", "mode": "explore"}),
        "Final Answer: s",
        "Final Answer: m",
    ]
    repl, _ = make(ws, cfg_file)
    repl.dispatch("/delegate on")
    repl.submit("main task")
    assert "Sub-agent summary:\ns" in scripted.calls[2].messages[-1].content


def test_delegate_on_enables_disabled_group(scripted, ws, tmp_path):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + '\n[tool_groups]\ndisabled = ["delegate"]\n', encoding="utf-8")
    repl, feed = make(ws, path)
    repl.dispatch("/delegate on")
    assert "tool group delegate: on" in feed.text
    assert "delegate" not in repl.agent.ctx.disabled_groups


def test_reset_restores_delegate_and_counters(scripted, ws, cfg_file):
    scripted.script[:] = [
        act("delegate", {"task": "t", "mode": "explore"}),
        _boom,
        "Final Answer: m",
    ]
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/delegate on")
    repl.submit("first task")
    fresh, _ = make(ws, cfg_file)
    feed.out.clear()
    repl.dispatch("/reset")
    assert "delegation: on -> off" in feed.text
    assert repl.snapshot() == fresh.snapshot()
    assert repl.delegate_override is None
    assert repl.session is None
    feed.out.clear()
    repl.dispatch("/cost")
    assert "No model calls yet" in feed.text
    scripted.script[:] = [
        act("delegate", {"task": "t", "mode": "explore"}),
        "Final Answer: s",
        "Final Answer: m",
    ]
    repl.dispatch("/delegate on")
    repl.submit("second task")
    assert "Sub-agent summary:\ns" in scripted.calls[-1].messages[-1].content
    assert repl.session.delegation_stats["explore_calls"] == 1


def test_reset_keeps_start_delegate_flag(scripted, ws, cfg_file):
    repl, _ = make(ws, cfg_file, delegate=True)
    repl.dispatch("/delegate off")
    repl.dispatch("/reset")
    assert repl.cfg.delegation.enabled is True


AUTO = CFG_TOML + "\n[tool_groups]\nauto_simple = true\n"


def test_delegate_on_forces_group_under_auto_simple(scripted, ws, tmp_path):
    path = tmp_path / "cora.toml"
    path.write_text(AUTO, encoding="utf-8")
    repl, _ = make(ws, path)
    repl.dispatch("/delegate on")
    assert "delegate" in repl.agent.ctx.forced_groups
    scripted.script[:] = ["Final Answer: a"]
    repl.submit("hi")
    assert "- delegate:" in scripted.calls[-1].messages[0].content
    repl.dispatch("/delegate off")
    assert "delegate" not in repl.agent.ctx.forced_groups
    repl.dispatch("/clear")
    scripted.script[:] = ["Final Answer: b"]
    repl.submit("hi")
    assert "- delegate:" not in scripted.calls[-1].messages[0].content
    repl.dispatch("/delegate on")
    repl.dispatch("/tools delegate off")
    assert "delegate" not in repl.agent.ctx.forced_groups
    repl.dispatch("/reset")
    assert "delegate" not in repl.agent.ctx.forced_groups


def test_config_delegation_keeps_auto_rule(scripted, ws, tmp_path):
    path = tmp_path / "cora.toml"
    path.write_text(AUTO + "\n[delegation]\nenabled = true\n", encoding="utf-8")
    repl, _ = make(ws, path)
    scripted.script[:] = ["Final Answer: a"]
    repl.submit("hi")
    assert "- delegate:" not in scripted.calls[0].messages[0].content
