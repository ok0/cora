from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.config import MemorySettings
from cora.core.memory import (
    WorkingMemory,
    normalize_read_path,
    read_path_of,
    superseded,
)
from cora.core.types import Message


def _sequence(m: WorkingMemory) -> None:
    m.add(Message("user", "Observation: A1"), read_path="a.py")
    m.add(Message("user", "Observation: B1"), read_path="b.py")
    m.add(Message("assistant", "thought"))
    m.add(Message("user", "Observation: A2"), read_path="a.py")


def test_dedupe_supersedes_earlier_read() -> None:
    m = WorkingMemory(MemorySettings(), dedupe_reads=True)
    _sequence(m)
    assert m.recent[0].content == "[superseded: a.py read again later]"
    assert m.recent[1].content == "Observation: B1"
    assert m.recent[3].content == "Observation: A2"

    m.add(Message("user", "Observation: A3"), read_path="a.py")
    assert m.recent[0].content == "[superseded: a.py read again later]"
    assert m.recent[3].content == "[superseded: a.py read again later]"
    assert m.recent[4].content == "Observation: A3"
    assert m.recent[1].content == "Observation: B1"


def test_dedupe_off_changes_nothing() -> None:
    m = WorkingMemory(MemorySettings())
    _sequence(m)
    assert [x.content for x in m.recent] == [
        "Observation: A1",
        "Observation: B1",
        "thought",
        "Observation: A2",
    ]
    assert "read_paths" not in m.to_dict()
    assert set(m.to_dict().keys()) == {"pinned", "summary_lines", "recent"}


def test_non_read_observations_untouched() -> None:
    m = WorkingMemory(MemorySettings(), dedupe_reads=True)
    m.add(Message("user", "Observation: X"))
    m.add(Message("user", "Observation: Y"))
    m.add(Message("tool", "out", tool_call_id="1"))
    assert [x.content for x in m.recent] == [
        "Observation: X",
        "Observation: Y",
        "out",
    ]
    assert "read_paths" not in m.to_dict()


def test_dedupe_survives_roundtrip_and_eviction() -> None:
    settings = MemorySettings(context_budget_tokens=200, keep_last_messages=2)
    m = WorkingMemory(settings, dedupe_reads=True)
    m.add(Message("user", "Observation: A1 " + "x" * 400), read_path="a.py")
    m.add(Message("assistant", "t1"))
    m.add(Message("user", "Observation: B1 " + "y" * 400), read_path="b.py")
    m.add(Message("assistant", "t2"))
    m.add(Message("user", "Observation: C1 " + "z" * 400), read_path="c.py")
    m.build("sys")
    assert len(m.read_paths) == len(m.recent)

    m.add(Message("user", "Observation: C2"), read_path="c.py")
    assert m.recent[-1].content == "Observation: C2"
    assert len(m.read_paths) == len(m.recent)

    fresh = WorkingMemory(MemorySettings(), dedupe_reads=True)
    _sequence(fresh)
    data = fresh.to_dict()
    assert "read_paths" in data
    restored = WorkingMemory.from_dict(data, MemorySettings(), None, "", dedupe_reads=True)
    assert restored.recent[0].content == "[superseded: a.py read again later]"
    assert restored.recent[1].content == "Observation: B1"
    restored.add(Message("user", "Observation: A3"), read_path="a.py")
    assert restored.recent[3].content == "[superseded: a.py read again later]"
    assert restored.recent[4].content == "Observation: A3"


def test_external_recent_assignment_is_safe() -> None:
    m = WorkingMemory(MemorySettings(context_budget_tokens=100_000), dedupe_reads=True)
    m.add(Message("user", "Observation: A1"), read_path="a.py")
    m.recent = [Message("user", "Observation: Z")]
    m.add(Message("user", "Observation: A2"), read_path="a.py")
    m.build("sys")
    assert m.recent[-1].content == "Observation: A2"
    assert len(m.read_paths) == len(m.recent)


@pytest.mark.parametrize(
    ("tool", "args", "ok", "expected"),
    [
        ("read_file", {"path": "./a.py"}, True, "a.py"),
        ("read_file", {"path": "sub/../a.py"}, True, "a.py"),
        ("read_file", {"path": "__ROOT__/x/y.py"}, True, "x/y.py"),
        ("read_file", {"path": "../out.py"}, True, None),
        ("list_files", {"path": "a.py"}, True, None),
        ("read_file", {"path": "a.py"}, False, None),
        ("read_file", None, True, None),
    ],
)
def test_read_path_of(
    tmp_path: Path, tool: str, args: object, ok: bool, expected: str | None
) -> None:
    root = tmp_path.resolve()
    if isinstance(args, dict) and isinstance(args.get("path"), str):
        args = {"path": args["path"].replace("__ROOT__", str(root))}
    assert read_path_of(root, tool, args, ok) == expected


def test_normalize_and_superseded_helpers(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    assert normalize_read_path(root, "a.py") == "a.py"
    assert superseded("a.py") == "[superseded: a.py read again later]"
