from __future__ import annotations

import json
from pathlib import Path

import m17b_counts as C


def test_count_loop_errors(tmp_path: Path) -> None:
    events = [
        {"type": "parse_error", "error": "bad json"},
        {"type": "parse_error", "error": "bad json again"},
        {
            "type": "tool_call",
            "tool": "edit_file",
            "ok": False,
            "output_head": C.OLD_NOT_FOUND + "a.py",
        },
        {
            "type": "tool_call",
            "tool": "edit_file",
            "ok": False,
            "output_head": "edit_file failed: something else",
        },
        {"type": "repeat_detected"},
        {"type": "reply_truncated"},
        {
            "type": "tool_call",
            "tool": "edit_file",
            "ok": False,
            "output_head": C.OLD_NOT_FOUND + "a.py (located at line 12; check indentation)",
        },
    ]
    log = tmp_path / "a/state/sessions/s1/events.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    assert C.count_loop_errors(tmp_path) == {
        "sessions": 1,
        "parse_error": 2,
        "old_not_found": 2,
        "loop_errors": 4,
        "repeat_detected": 1,
        "reply_truncated": 1,
        "parse_repaired": 0,
    }
