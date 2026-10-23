from __future__ import annotations

import json
import sys
from pathlib import Path

OLD_NOT_FOUND = "edit_file failed: 'old' text not found in "


def count_loop_errors(root: Path) -> dict[str, int]:
    counts = {
        "sessions": 0,
        "parse_error": 0,
        "old_not_found": 0,
        "repeat_detected": 0,
        "reply_truncated": 0,
        "parse_repaired": 0,
    }
    for path in sorted(root.rglob("events.jsonl")):
        counts["sessions"] += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            kind = event.get("type")
            if kind == "parse_error":
                counts["parse_error"] += 1
            elif kind == "tool_call":
                if (
                    event.get("tool") == "edit_file"
                    and event.get("ok") is False
                    and str(event.get("output_head", "")).startswith(OLD_NOT_FOUND)
                ):
                    counts["old_not_found"] += 1
            elif kind == "repeat_detected":
                counts["repeat_detected"] += 1
            elif kind == "reply_truncated":
                counts["reply_truncated"] += 1
            elif kind == "parse_repaired":
                counts["parse_repaired"] += 1
    counts["loop_errors"] = counts["parse_error"] + counts["old_not_found"]
    return counts


def main(argv: list[str]) -> int:
    for p in argv:
        counts = count_loop_errors(Path(p))
        print(json.dumps({"root": p, **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
