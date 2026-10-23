from __future__ import annotations

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from conftest import run_repl
from cora.cli.io import MentionCompleter
from cora.core.mentions import expand_mentions, mention_candidates
from cora.core.state import SessionStore


def _expand(ws, prompt, **kw):
    limits = {"max_file_chars": 100, "max_total_chars": 1000, "max_dir_entries": 10}
    limits.update(kw)
    return expand_mentions(prompt, ws, **limits)


def test_expand_file(ws):
    (ws / "a.txt").write_text("hello world", encoding="utf-8")
    exp = _expand(ws, "explain @a.txt please")
    assert "--- @a.txt ---" in exp.text
    assert "hello world" in exp.text
    assert exp.attached == ("a.txt",)
    assert exp.notes == ()


def test_expand_caps(ws):
    (ws / "f1.txt").write_text("X" * 500, encoding="utf-8")
    (ws / "f2.txt").write_text("Y" * 500, encoding="utf-8")
    (ws / "f3.txt").write_text("Z" * 500, encoding="utf-8")
    exp = _expand(ws, "@f1.txt @f2.txt @f3.txt", max_file_chars=200, max_total_chars=450)
    assert exp.text.count("X") <= 200
    assert "[truncated]" in exp.text
    assert len(exp.text) <= 450
    assert any("truncated" in n for n in exp.notes)
    assert any("limit" in n for n in exp.notes) or exp.text.count("Z") < 500


def test_trailing_punctuation(ws):
    (ws / "a.txt").write_text("hi", encoding="utf-8")
    exp = _expand(ws, "see @a.txt.")
    assert exp.attached == ("a.txt",)


def test_directory_listing(ws):
    sub = ws / "sub"
    (sub / "inner").mkdir(parents=True)
    (sub / "__pycache__").mkdir()
    (sub / "f1.txt").write_text("x", encoding="utf-8")
    exp = _expand(ws, "@sub")
    assert "f1.txt" in exp.text
    assert "inner/" in exp.text
    assert "__pycache__" not in exp.text
    exp = _expand(ws, "@sub", max_dir_entries=1)
    assert "... (1 more)" in exp.text


def test_rejections(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (ws / "link.txt").symlink_to(outside)
    (ws / "bin.dat").write_bytes(b"\x00\x01")
    cases = [
        ("@../outside.txt", "outside the workspace"),
        (f"@{outside}", "outside the workspace"),
        ("@link.txt", "outside the workspace"),
        ("@missing.txt", "not found"),
        ("@bin.dat", "binary"),
    ]
    for prompt, expected in cases:
        exp = _expand(ws, prompt)
        assert exp.text == "", prompt
        assert any(expected in n for n in exp.notes), (prompt, exp.notes)


def test_email_and_escape_not_expanded(ws):
    (ws / "a.txt").write_text("x", encoding="utf-8")
    (ws / "b.com").write_text("x", encoding="utf-8")
    exp = _expand(ws, "mail a@b.com and \\@a.txt")
    assert exp.text == ""
    assert exp.notes == ()


def test_mention_candidates(ws):
    (ws / "src").mkdir()
    (ws / "src" / "main.py").write_text("x", encoding="utf-8")
    (ws / ".hidden").write_text("x", encoding="utf-8")
    (ws / ".git").mkdir()
    assert mention_candidates(ws, "s") == ["src/"]
    assert mention_candidates(ws, "src/m") == ["src/main.py"]
    assert mention_candidates(ws, "../") == []
    assert mention_candidates(ws, "/etc") == []
    listed = mention_candidates(ws, "")
    assert ".hidden" not in listed
    assert ".git/" not in listed


def test_mention_completer(ws):
    (ws / "src").mkdir()
    completer = MentionCompleter(ws)
    event = CompleteEvent()

    def texts(s):
        return [c.text for c in completer.get_completions(Document(s), event)]

    assert texts("look at @sr") == ["src/"]
    assert texts("a@sr") == []
    assert texts("/he") == []


def test_repl_mentions_reach_model(scripted, ws, cfg_file):
    (ws / "a.txt").write_text("MENTION-CONTENT", encoding="utf-8")
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["explain @a.txt and @nope.txt", "/exit"])
    assert "MENTION-CONTENT" in scripted.calls[0].messages[1].content
    assert "@nope.txt: not found" in out
    store = SessionStore(ws / ".cora" / "sessions")
    sid = store.list_ids()[-1]
    assert store.load(sid).task == "explain @a.txt and @nope.txt"
