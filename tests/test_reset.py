from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CFG_TOML, act, native, run_repl, tc, write_files
from cora.cli.io import PlainIO
from cora.cli.repl import Repl, ReplOptions
from cora.core.config import ModelOverride, save_user_overrides, user_models_path
from cora.core.state import SessionStore

NATIVE_TOML = CFG_TOML + '\n[agent]\ntool_protocol = "native"\n'


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


class Proto:
    def __init__(self, name: str, cfg: Path) -> None:
        self.name, self.cfg = name, cfg

    def call(self, tool, args):
        return act(tool, args) if self.name == "react" else native(tc(tool, args))

    def final(self, text):
        return f"Final Answer: {text}" if self.name == "react" else native(text=text)


@pytest.fixture(params=["react", "native"])
def proto(request, tmp_path) -> Proto:
    path = tmp_path / "proto.toml"
    path.write_text(CFG_TOML if request.param == "react" else NATIVE_TOML, encoding="utf-8")
    return Proto(request.param, path)


def make(ws, cfg, *, approval="ask", delegate=False) -> tuple[Repl, Feed]:
    feed = Feed()
    repl = Repl(
        PlainIO(input_fn=feed.read, write=feed.out.append),
        ReplOptions(Path(ws), Path(cfg), approval=approval, delegate=delegate),
    )
    return repl, feed


def _save_override(ws) -> Path:
    path = user_models_path(Path(ws).resolve())
    save_user_overrides(path, {"strong": ModelOverride("strong", "x/strong", None, 1.0, 2.0)})
    return path


def _total_cost(ws) -> float:
    store = SessionStore(ws / ".cora" / "sessions")
    return sum(r["cost_usd"] for sid in store.list_ids() for r in store.load(sid).meter)


def test_reset_restores_start_state(proto, scripted, ws):
    write_files(ws, {"a.txt": "MENTION_MARKER\n"})
    scripted.script[:] = [
        proto.call("todo_write", {"todos": [{"content": "step one", "status": "pending"}]}),
        proto.call("edit_file", {"path": "a.txt", "old": "MENTION_MARKER", "new": "EDITED"}),
        proto.final("done"),
    ]
    repl, feed = make(ws, proto.cfg)
    start = repl.snapshot()
    feed.answers[:] = ["a"]
    repl.submit("edit @a.txt please")
    repl.dispatch("/approval auto")
    repl.dispatch("/model pin mock/strong")
    repl.dispatch("/tools web off")
    repl.dispatch("/check echo ok")
    repl.dispatch("/plan")
    s = repl.snapshot()
    assert s.approval == "auto"
    assert s.always_allowed != "none"
    assert s.pin == "mock/strong"
    assert s.tool_groups == "web=off"
    assert s.check == "echo ok"
    assert s.plan_mode == "on"
    assert s.todos == "1"
    assert s.session != "new"
    assert s.edited_files == "1"
    repl.dispatch("/reset")
    fresh, _ = make(ws, proto.cfg)
    assert repl.snapshot() == fresh.snapshot() == start
    assert repl.cfg == fresh.cfg
    assert repl.opts == fresh.opts
    assert repl.pin is None
    assert repl.check_command is None
    assert repl.plan_mode is False
    assert repl.group_overrides == {}
    assert repl.todos.items == []
    assert repl.session is None
    assert repl.policy.mode == "ask"
    assert repl.policy.always_allowed == set()
    assert repl.agent.ctx.disabled_groups == fresh.agent.ctx.disabled_groups
    assert repl.agent.ctx.forced_groups == fresh.agent.ctx.forced_groups
    assert repl.agent.ctx.plan_mode is False
    assert repl.agent.ctx.todos is repl.todos
    assert repl.agent.ctx.originals == {}
    scripted.script[:] = [proto.final("after")]
    repl.submit("next request")
    msgs = " ".join(m.content for m in scripted.calls[-1].messages)
    assert "MENTION_MARKER" not in msgs
    assert "edit @a.txt" not in msgs


@pytest.mark.parametrize("delegate", [False, True])
def test_reset_keeps_start_flags(ws, cfg_file, delegate):
    repl, _ = make(ws, cfg_file, approval="deny", delegate=delegate)
    repl.dispatch("/approval auto")
    repl.dispatch("/reset")
    fresh, _ = make(ws, cfg_file, approval="deny", delegate=delegate)
    assert repl.cfg.delegation.enabled is delegate
    assert repl.snapshot() == fresh.snapshot()
    assert repl.policy.mode == "deny"
    assert repl.opts == fresh.opts


def test_reset_leaves_models_toml_bytes(scripted, ws, cfg_file):
    path = _save_override(ws)
    data = path.read_bytes()
    repl, _ = make(ws, cfg_file)
    repl.dispatch("/model pin mock/cheap")
    repl.dispatch("/plan")
    repl.dispatch("/reset")
    assert path.read_bytes() == data
    assert "strong=x/strong" in repl.snapshot().models


@pytest.mark.parametrize("answers", [["n"], [""], []])
def test_reset_all_refused_changes_nothing(scripted, ws, cfg_file, answers):
    path = _save_override(ws)
    data = path.read_bytes()
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/plan")
    repl.dispatch("/check echo ok")
    before = repl.snapshot()
    feed.answers[:] = answers
    repl.dispatch("/reset --all")
    assert path.read_bytes() == data
    assert repl.snapshot() == before
    assert "reset cancelled; nothing changed" in feed.text


def test_reset_all_confirmed_deletes_overrides(scripted, ws, cfg_file):
    path = _save_override(ws)
    repl, feed = make(ws, cfg_file)
    assert "strong=x/strong" in repl.snapshot().models
    repl.dispatch("/plan")
    feed.answers[:] = ["y"]
    repl.dispatch("/reset --all")
    assert not path.exists()
    fresh, _ = make(ws, cfg_file)
    assert repl.snapshot() == fresh.snapshot()
    assert "strong=mock/strong" in repl.snapshot().models
    assert "saved model overrides: deleted" in feed.text
    assert "[y/N]" in feed.text


def test_reset_keeps_saved_sessions_and_starts_new(proto, scripted, ws):
    scripted.script[:] = [proto.final("one"), proto.final("two")]
    repl, feed = make(ws, proto.cfg)
    repl.submit("first task")
    first = repl.session.id
    repl.dispatch("/reset")
    assert repl.session is None
    assert f"session: {first} -> new (saved; /resume {first} reopens it)" in feed.text
    repl.dispatch("/sessions")
    assert first in feed.text
    repl.submit("second task")
    second = repl.session.id
    assert second != first
    assert set(SessionStore(ws / ".cora" / "sessions").list_ids()) == {first, second}
    repl.dispatch(f"/resume {first}")
    assert repl.session.id == first
    assert f"Resumed session {first}" in feed.text


def test_reset_summary_lists_only_changes(scripted, ws, cfg_file):
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/reset")
    assert "reset: nothing changed (already at the REPL start state)" in feed.text
    repl.dispatch("/approval auto")
    repl.dispatch("/plan")
    feed.out.clear()
    repl.dispatch("/reset")
    text = feed.text
    assert "reset to the REPL start state:" in text
    assert "  approval: auto -> ask" in text
    assert "  plan mode: on -> off" in text
    for label in (
        "models:",
        "model pin:",
        "always-allowed",
        "tool group",
        "check:",
        "delegation:",
        "TODO items:",
        "session:",
        "files tracked",
    ):
        assert label not in text


def test_reset_keeps_process_cost(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: one", "Final Answer: two"]
    repl, feed = make(ws, cfg_file)
    repl.submit("first task")
    before = _total_cost(ws)
    assert before > 0
    repl.dispatch("/reset")
    assert _total_cost(ws) == before
    repl.dispatch("/cost")
    assert "No model calls yet in this session ($0.00)." in feed.text
    repl.submit("second task")
    new = sum(r["cost_usd"] for r in repl.session.meter)
    assert new > 0
    assert _total_cost(ws) == pytest.approx(before + new)


@pytest.mark.parametrize(
    ("start", "looser"), [("ask", "auto"), ("deny", "auto"), ("deny", "ask")]
)
def test_reset_restores_start_approval(ws, cfg_file, start, looser):
    repl, _ = make(ws, cfg_file, approval=start)
    repl.dispatch(f"/approval {looser}")
    repl.dispatch("/reset")
    assert repl.policy.mode == start


def test_reset_ignores_config_loosened_mid_session(scripted, ws, tmp_path):
    cfg = tmp_path / "loose.toml"
    cfg.write_text(CFG_TOML + '\n[agent]\napproval = "ask"\n', encoding="utf-8")
    repl, _ = make(ws, cfg, approval=None)
    assert repl.policy.mode == "ask"
    cfg.write_text(CFG_TOML + '\n[agent]\napproval = "auto"\n', encoding="utf-8")
    repl.dispatch("/reset")
    assert repl.policy.mode == "ask"


def test_reset_typed_at_approval_prompt_is_a_denial(scripted, ws, cfg_file):
    write_files(ws, {"a.txt": "hello\n"})
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: x",
    ]
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/tools web off")
    feed.answers[:] = ["/reset"]
    repl.submit("edit it")
    assert (ws / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert "denied by user" in feed.text
    assert repl.group_overrides == {"web": False}
    assert repl.policy.always_allowed == set()


@pytest.mark.parametrize(
    "cmd", ["/reset foo", "/reset --all now", "/reset --ALL", "/reset all"]
)
def test_reset_usage_error_changes_nothing(scripted, ws, cfg_file, cmd):
    repl, feed = make(ws, cfg_file)
    repl.dispatch("/plan")
    repl.dispatch("/check echo ok")
    before = repl.snapshot()
    repl.dispatch(cmd)
    assert "error: usage: /reset [--all]" in feed.text
    assert repl.snapshot() == before
    assert "[y/N]" not in feed.text


def test_reset_via_run_loop_and_help(scripted, ws, cfg_file):
    out = run_repl(ws, cfg_file, ["/help", "/reset", "/exit"])
    assert "/reset" in out
    assert "reset: nothing changed" in out
