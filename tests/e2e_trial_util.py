from __future__ import annotations

import json
import sys
from pathlib import Path

from cora.bench import e2e


def _task(task_id: str) -> e2e.E2ETask:
    return e2e.select_e2e_tasks([task_id])[0]


def prepare(task_id: str, d: Path | str) -> Path:
    task = _task(task_id)
    return e2e.prepare_workspace(task, Path(d))


def grade(task_id: str, ws: Path | str, scratch: Path | str) -> dict:
    task = _task(task_id)
    g = e2e.run_grader(task, Path(ws), Path(scratch))
    return g.to_dict()


def leakcheck(task_id: str, ws: Path | str, *, pre_grade: bool = False) -> list[str]:
    task = _task(task_id)
    needles = (str(task.root), str(task.grader_dir), str(task.reference_dir), ".cora_grader")
    root = Path(ws)
    leaks: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == e2e.GRADER_DIRNAME:
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle in text for needle in needles):
            leaks.append(rel.as_posix())
    if pre_grade and (root / e2e.GRADER_DIRNAME).exists():
        leaks.insert(0, e2e.GRADER_DIRNAME)
    return leaks


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: e2e_trial_util.py prepare|grade|leakcheck [--pre-grade] ...", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "prepare" and len(rest) == 2:
        print(prepare(rest[0], rest[1]))
        return 0
    if cmd == "grade" and len(rest) == 3:
        print(json.dumps(grade(rest[0], rest[1], rest[2])))
        return 0
    if cmd == "leakcheck" and (len(rest) == 2 or (len(rest) == 3 and rest[2] == "--pre-grade")):
        leaks = leakcheck(rest[0], rest[1], pre_grade=len(rest) == 3)
        print(json.dumps(leaks))
        return 1 if leaks else 0
    print(f"bad command: {' '.join(argv)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
