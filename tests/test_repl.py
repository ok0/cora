from __future__ import annotations

import shutil
import subprocess

import pytest

from conftest import CFG_TOML, act, run_repl, write_files
from cora.cli.io import PlainIO
from cora.cli.repl import COMMANDS, Repl, ReplOptions
from cora.core.errors import CoraError
from cora.core.observability import read_events
from cora.core.state import SessionStore


def _store(ws) -> SessionStore:
    return SessionStore(ws / ".cora" / "sessions")


def _session_ids(ws) -> list[str]:
    return _store(ws).list_ids()


def _contents(messages) -> list[str]:
    return [m.content for m in messages]


def test_request_answer_exit(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: the answer"]
    out = run_repl(ws, cfg_file, ["hello", "/exit"])
    assert "the answer" in out
    assert "tokens" in out
    assert "== CORA cost summary ==" in out


def test_help_and_unknown(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: still alive"]
    out = run_repl(ws, cfg_file, ["/help", "/foo", "hi", "/exit"])
    for name in COMMANDS:
        assert name in out
    assert "Unknown command: /foo" in out
    assert "Type /help" in out
    assert "still alive" in out


def test_multiline_and_ctrl_c_at_prompt(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, [KeyboardInterrupt(), "line one \\", "line two", "/exit"])
    assert any("Task: line one \nline two" in c for c in _contents(scripted.calls[0].messages))
    assert "Ctrl-D or /exit" in out


def test_approval_ask_diff_and_always(scripted, ws, cfg_file):
    write_files(ws, {"a.txt": "hello\n"})
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: d1",
        act("edit_file", {"path": "a.txt", "old": "bye", "new": "ciao"}),
        "Final Answer: d2",
    ]
    out = run_repl(
        ws,
        cfg_file,
        ["edit it", "a", "edit again", "/exit"],
        approval="ask",
    )
    assert "-hello" in out
    assert "+bye" in out
    assert "● edit_file a.txt" in out
    assert out.count("Allow?") == 1
    assert (ws / "a.txt").read_text(encoding="utf-8") == "ciao\n"


def test_approval_command_modes(scripted, ws, cfg_file):
    write_files(ws, {"a.txt": "hello\n"})
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: x",
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: y",
    ]
    out = run_repl(
        ws,
        cfg_file,
        [
            "/approval",
            "/approval deny",
            "edit it",
            "/approval auto",
            "edit it",
            "/approval bogus",
            "/exit",
        ],
        approval="ask",
    )
    assert "approval mode: ask" in out
    assert "failed: denied by user" in out
    assert (ws / "a.txt").read_text(encoding="utf-8") == "bye\n"
    assert "Allow?" not in out
    assert "invalid approval mode 'bogus'" in out


def test_cost_status_sessions(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["/cost", "hi", "/cost", "/status", "/sessions", "/exit"])
    assert "No model calls yet" in out
    assert "== CORA cost summary ==" in out
    assert "mock/cheap" in out
    assert str(ws.resolve()) in out
    assert "approval: auto" in out
    (sid,) = _session_ids(ws)
    assert sid in out


def test_clear_starts_new_session(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: one", "Final Answer: two"]
    run_repl(ws, cfg_file, ["first task", "/clear", "second task", "/exit"])
    assert len(_session_ids(ws)) == 2
    assert not any("first task" in c for c in _contents(scripted.calls[1].messages))


def test_compact(scripted, ws, cfg_file):
    scripted.script[:] = [act("list_files", {})] * 3 + ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["list", "/compact", "/exit"])
    assert "Compacted 5 messages" in out
    (sid,) = _session_ids(ws)
    memory = _store(ws).load(sid).memory
    assert len(memory["recent"]) == 2
    out = run_repl(ws, cfg_file, ["/compact", "/exit"])
    assert "Nothing to compact." in out


def test_resume_by_id_and_picker(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: one"]
    run_repl(ws, cfg_file, ["first task", "/exit"])
    (sid,) = _session_ids(ws)

    scripted.script[:] = ["Final Answer: two"]
    out = run_repl(ws, cfg_file, [f"/resume {sid}", "second", "/exit"])
    assert "Resumed session" in out
    assert any("Task: first task" in c for c in _contents(scripted.calls[-1].messages))

    scripted.script[:] = ["Final Answer: three"]
    out = run_repl(ws, cfg_file, ["/resume", "1", "third", "/exit"])
    assert "Resumed session" in out
    assert any("Task: first task" in c for c in _contents(scripted.calls[-1].messages))

    out = run_repl(ws, cfg_file, ["/resume nope", "/exit"])
    assert "session not found" in out


def test_diff_without_git(scripted, ws, cfg_file):
    write_files(ws, {"a.txt": "hello\n"})
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: ok",
    ]
    out = run_repl(ws, cfg_file, ["/diff", "edit", "/diff", "/exit"])
    assert "No files changed in this session." in out
    assert "-hello" in out
    assert "+bye" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_diff_with_git(scripted, ws, cfg_file):
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    write_files(ws, {"a.txt": "hello\n"})
    subprocess.run(["git", "add", "a.txt"], cwd=ws, check=True)
    scripted.script[:] = [
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: ok",
    ]
    out = run_repl(ws, cfg_file, ["edit", "/diff", "/exit"])
    assert "+bye" in out


def test_init_creates_and_never_overwrites(ws, cfg_file):
    out = run_repl(ws, cfg_file, ["/init", "/init", "/exit"])
    assert "Created CORA.md" in out
    assert "already exists" in out
    assert (ws / "CORA.md").read_text(encoding="utf-8").startswith("# CORA.md")
    (ws / "CORA.md").write_text("custom", encoding="utf-8")
    run_repl(ws, cfg_file, ["/init", "/exit"])
    assert (ws / "CORA.md").read_text(encoding="utf-8") == "custom"


def test_guide_injected_and_shown(scripted, ws, cfg_file):
    write_files(ws, {"AGENTS.md": "AGENTS-RULE-XYZ", "CLAUDE.md": "CLAUDE-RULE"})
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["hi", "/exit"])
    assert "guide: AGENTS.md" in out
    system = scripted.calls[0].messages[0].content
    assert "AGENTS-RULE-XYZ" in system
    assert "CLAUDE-RULE" not in system

    write_files(ws, {"CORA.md": "CORA-RULE"})
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["hi", "/exit"])
    assert "guide: CORA.md" in out
    assert "CORA-RULE" in scripted.calls[1].messages[0].content


def test_ctrl_c_during_turn_keeps_session(scripted, ws, cfg_file):
    def ki(req):
        raise KeyboardInterrupt

    scripted.script[:] = [ki, "Final Answer: after"]
    out = run_repl(ws, cfg_file, ["first task", "second task", "/exit"])
    assert "Interrupted" in out
    assert "after" in out
    (sid,) = _session_ids(ws)
    assert any("Task: first task" in c for c in _contents(scripted.calls[1].messages))
    assert _store(ws).load(sid).state.value == "done"


def test_streaming_answer_printed_once(scripted, ws, tmp_path):
    cfg = tmp_path / "stream.toml"
    cfg.write_text(
        CFG_TOML.replace('provider = "scripted"', 'provider = "scripted_stream"'),
        encoding="utf-8",
    )
    scripted.script[:] = ["Thought: t\nFinal Answer: streamed hello"]
    out = run_repl(ws, cfg, ["hi", "/exit"])
    assert out.count("streamed hello") == 1
    (sid,) = _session_ids(ws)
    events = read_events(_store(ws).dir_for(sid) / "events.jsonl")
    llm = [e for e in events if e["type"] == "llm_call"]
    assert len(llm) == 1
    assert llm[0]["input_tokens"] > 0


def test_initial_resume_restores_context(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: one"]
    run_repl(ws, cfg_file, ["first task", "/exit"])
    (sid,) = _session_ids(ws)

    scripted.calls.clear()
    scripted.script[:] = ["Final Answer: two"]
    out: list[str] = []
    feed = ["second", "/exit"]

    def read(prompt: str) -> str:
        out.append(prompt)
        if not feed:
            raise EOFError
        return feed.pop(0)

    rc = Repl(PlainIO(input_fn=read, write=out.append),
              ReplOptions(ws, cfg_file, approval="auto", resume_id=sid)).run()
    assert rc == 0
    text = "".join(out)
    assert f"Resumed session {sid}" in text
    assert "> first task" in text
    assert "one" in text
    assert text.index("Resumed session") < text.index("two")
    contents = _contents(scripted.calls[0].messages)
    assert any("Task: first task" in c for c in contents)
    assert any("New request: second" in c for c in contents)
    assert f"session: {sid}" in text


def test_initial_resume_unknown_id_raises(ws, cfg_file):
    with pytest.raises(CoraError, match="session not found"):
        Repl(PlainIO(input_fn=lambda p: "/exit", write=lambda s: None),
             ReplOptions(ws, cfg_file, resume_id="nope"))
