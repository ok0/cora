from __future__ import annotations

from pathlib import Path

from cora.core.config import MemorySettings
from cora.core.memory import (
    LEDGER_HEADER,
    PROTECTED_MARK,
    REDACTED_MARK,
    SUMMARY_INPUT_CHARS,
    SUMMARY_SYSTEM,
    PersistentStore,
    WorkingMemory,
    WorkingStateLedger,
    mask_command,
    mask_path,
    scrub_secrets,
    summary_messages,
)
from cora.core.shellguard import PathGuard, default_protected
from cora.core.types import Message


def _filled() -> WorkingStateLedger:
    led = WorkingStateLedger()
    led.note_file("a.py", "edit", 1)
    led.note_file("a.py", "edit", 2)
    led.note_file("a.py", "edit", 3)
    led.note_file("b.py", "write", 4)
    led.note_check("pytest -q", False, 5, "boom\nAssertionError")
    led.note_check("pytest -q", True, 6, "")
    led.note_decision("gate", "compile_check (edit)", 6)
    led.note_read_evicted("big.txt")
    return led


def _big() -> WorkingStateLedger:
    led = WorkingStateLedger()
    for i in range(12):
        led.note_file(f"src/file{i}.py", "edit", i)
    for i in range(30):
        led.note_check(f"check-cmd-{i}", i % 2 == 0, i, f"out {i}")
    for i in range(20):
        led.note_decision("gate", f"decision text {i}", i)
    for i in range(5):
        led.add_summary(f"summary line {i}")
    return led


def test_records_and_renders() -> None:
    text = _filled().render(1500)
    assert "a.py" in text
    assert "b.py" in text
    assert "FAIL" in text
    assert "PASS" in text
    assert "gate" in text
    assert "big.txt" in text


def test_render_deterministic() -> None:
    a = _filled().render(1500)
    b = _filled().render(1500)
    assert a == b
    assert _filled().render(1500) == a


def test_render_bounded_and_keeps_latest_and_paths() -> None:
    led = _big()
    for max_chars in (300, 600, 1500):
        assert len(led.render(max_chars)) <= max_chars
    for max_chars in (600, 1500):
        text = led.render(max_chars)
        for i in range(12):
            assert f"src/file{i}.py" in text
        assert "check-cmd-29" in text
    assert "`check-cmd-0`" not in led.render(600)


def test_decision_collapse() -> None:
    led = WorkingStateLedger()
    led.note_decision("gate", "same", 1)
    led.note_decision("gate", "same", 2)
    assert "(x2)" in led.render(1500)


def test_record_false_keeps_only_summaries() -> None:
    led = WorkingStateLedger(record=False)
    led.note_file("a.py", "edit", 1)
    led.note_check("pytest", True, 1, "")
    led.note_decision("gate", "x", 1)
    led.note_read_evicted("b.txt")
    assert led.files == {}
    assert led.checks == []
    assert led.decisions == []
    assert led.read_evicted == []
    assert led.add_summary("a\nb") == "a b"
    assert "Earlier steps: a b" in led.render(1500)


def test_evicted_read_noted_without_content() -> None:
    mem = WorkingMemory(
        MemorySettings(context_budget_tokens=400, keep_last_messages=1, ledger=True)
    )
    mem.pin(Message("user", "Task: x"))
    for i in range(6):
        mem.add(
            Message("tool", "SECRETCONTENT" * 40, tool_call_id=f"c{i}"),
            read_path=f"f{i}.txt",
        )
    msgs = mem.build("sys")
    assert msgs[0].role == "system"
    assert any(m.content == "Task: x" for m in msgs)
    assert mem.ledger is not None
    assert "f0.txt" in mem.ledger.render(1500)
    ledger_msgs = [m.content for m in msgs if m.content.startswith(LEDGER_HEADER)]
    assert all("SECRETCONTENT" not in c for c in ledger_msgs)
    assert "SECRETCONTENT" not in mem.ledger.render(1500)
    assert mem.drain_evicted()
    assert mem.drain_evicted() == []


def test_read_back_removes() -> None:
    led = WorkingStateLedger()
    led.note_read_evicted("big.txt")
    assert "big.txt" in led.read_evicted
    mem = WorkingMemory(MemorySettings(ledger=True))
    assert mem.ledger is not None
    mem.ledger.note_read_evicted("big.txt")
    mem.add(Message("tool", "content"), read_path="big.txt")
    assert "big.txt" not in mem.ledger.read_evicted


def test_evicted_record_has_read_path_only_with_ledger(tmp_path: Path) -> None:
    store = PersistentStore(tmp_path)

    def run(sid: str, ledger: bool) -> None:
        mem = WorkingMemory(
            MemorySettings(context_budget_tokens=200, keep_last_messages=1, ledger=ledger),
            store,
            sid,
        )
        for i in range(4):
            mem.add(Message("tool", "x" * 300, tool_call_id=f"c{i}"), read_path=f"r{i}.txt")
        mem.build("sys")

    run("on", True)
    run("off", False)
    on_rows = store.read("on", "evicted")
    off_rows = store.read("off", "evicted")
    assert on_rows
    assert off_rows
    assert any("read_path" in r["data"] for r in on_rows)
    for r in off_rows:
        assert set(r["data"].keys()) == {"role", "content"}


def test_roundtrip_and_old_session() -> None:
    settings_on = MemorySettings(ledger=True)
    mem = WorkingMemory(settings_on)
    assert mem.ledger is not None
    mem.ledger.note_file("a.py", "edit", 1)
    mem.ledger.note_check("pytest", False, 2, "boom")
    mem.ledger.add_summary("did things")
    data = mem.to_dict()
    restored = WorkingMemory.from_dict(data, settings_on, None, "s")
    assert restored.ledger is not None
    assert restored.ledger.render(1500) == mem.ledger.render(1500)

    old = WorkingMemory.from_dict(
        {"pinned": [], "recent": [], "summary_lines": []}, settings_on, None, "s"
    )
    assert old.ledger is not None
    assert old.ledger.is_empty()

    odd = WorkingMemory.from_dict(
        {
            "pinned": [],
            "recent": [],
            "summary_lines": [],
            "ledger": {"files": 5, "checks": [1, "x"]},
        },
        settings_on,
        None,
        "s",
    )
    assert odd.ledger is not None
    assert odd.ledger.is_empty()

    off = WorkingMemory(MemorySettings(ledger=False))
    assert "ledger" not in off.to_dict()


def test_mask_path(tmp_path: Path) -> None:
    guard = PathGuard(tmp_path, default_protected())
    assert mask_path(tmp_path, guard, "a.py") == "a.py"
    assert mask_path(tmp_path, guard, ".env") == PROTECTED_MARK
    assert mask_path(tmp_path, guard, "/etc/passwd") == PROTECTED_MARK
    assert mask_path(tmp_path, guard, 5) is None


def test_mask_command(tmp_path: Path) -> None:
    guard = PathGuard(tmp_path, default_protected())
    assert mask_command(guard, "cat .env; pytest") == PROTECTED_MARK
    assert mask_command(guard, "pytest -q") == "pytest -q"


def test_scrub_secrets() -> None:
    env = {"MY_API_KEY": "sk-abcdef123"}
    assert scrub_secrets("x sk-abcdef123 y", env, ()) == f"x {REDACTED_MARK} y"
    assert scrub_secrets("abc", {"MY_API_KEY": "abc"}, ()) == "abc"


def test_summary_messages_hide_reads() -> None:
    evicted: list[tuple[Message, str | None]] = [
        (Message("tool", "SECRET_BODY line", tool_call_id="1"), "f.txt"),
        (Message("user", "hello"), None),
    ]
    out = summary_messages(evicted)
    assert out[0].role == "system"
    assert out[0].content == SUMMARY_SYSTEM
    assert "SECRET_BODY" not in out[1].content
    assert "[read f.txt]" in out[1].content
    assert sum(len(m.content) for m in out if m.role == "user") <= SUMMARY_INPUT_CHARS
    big = [(Message("user", "y" * 300), None) for _ in range(100)]
    capped = summary_messages(big)
    assert len(capped[1].content) <= SUMMARY_INPUT_CHARS
