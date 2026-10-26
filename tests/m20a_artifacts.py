"""Copy M20 run artifacts into a committed fixture dir, sanitized (M20a step 0).

Usage: uv run python tests/m20a_artifacts.py copy --src "$TMPDIR/cora-m20" --dst tests/fixtures/m20/artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

GROUPS = ("v2", "p2", "rr", "p1", "p1b", "p1c", "g0", "g0b", "g0c")
PLAN_GROUPS = {"p1", "p1b", "p1c", "g0", "g0b", "g0c"}
NAMES = ("outcome.json", "plan.toml", "events.jsonl")
TOP_FILES = ("cora-m20-deepseek.toml",)
KEY_RES = (
    re.compile(r"sk-or-v1-[0-9a-f]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
)
PARTIAL_TMP_RE = re.compile(r"(?:/private)?/var/folders/[^\s\"'\\]*")
PARTIAL_TMP = "<TMP-PARTIAL>"
PLACEHOLDERS = {
    "<M20>": "M20 source directory",
    "<TMP>": "system temp directory",
    "<HOME>": "home directory",
    "<TMP-PARTIAL>": (
        "truncated fragment of a system temp path (macOS per-user temp prefix) "
        "cut off by the recorder"
    ),
}


def _replacements(src: str) -> list[tuple[str, str]]:
    pairs: dict[str, str] = {}
    for s in {src, os.path.normpath(src), os.path.realpath(src), str(Path(src))}:
        pairs[s] = "<M20>"
    tmp = tempfile.gettempdir()
    for t in {tmp, os.path.normpath(tmp), os.path.realpath(tmp)}:
        pairs[t] = "<TMP>"
    pairs[os.path.expanduser("~")] = "<HOME>"
    return sorted(pairs.items(), key=lambda kv: len(kv[0]), reverse=True)


def _sanitize(text: str, pairs: list[tuple[str, str]]) -> tuple[str, list[int]]:
    lines = []
    partial_lines = []
    for n, line in enumerate(text.split("\n"), start=1):
        for old, new in pairs:
            line = line.replace(old, new)
        line, count = PARTIAL_TMP_RE.subn(PARTIAL_TMP, line)
        if count:
            partial_lines.append(n)
        lines.append(line)
    return "\n".join(lines), partial_lines


def _absent_reason(group: str, rdir: Path) -> tuple[str, list | None]:
    if group in PLAN_GROUPS:
        return "absent at source (plan-only run)", None
    outcome = rdir / "outcome.json"
    if outcome.is_file():
        data = json.loads(_read(outcome))
        if (
            data.get("session_id") is None
            and data.get("run_id") is None
            and data.get("iterations") == 0
        ):
            return "absent at source (no session started: planner error)", data["errors"]
    return "absent at source (unexplained)", None


def _dest_rel(parts: tuple[str, ...]) -> str:
    items = list(parts)
    for i in range(len(items) - 1):
        if items[i] == "ws" and items[i + 1] == ".cora":
            del items[i : i + 2]
            break
    return "/".join(items)


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def _key_hits(rel: str, text: str, literals: list[str]) -> list[str]:
    hits = []
    for rx in KEY_RES:
        if rx.search(text):
            hits.append(f"{rel}: pattern {rx.pattern}")
    for lit in literals:
        if lit in text:
            hits.append(f"{rel}: literal key value from environment")
    return hits


def copy(src: str, dst: str) -> int:
    src_dir = Path(src)
    dst_dir = Path(dst)
    pairs = _replacements(src)
    written: dict[str, str] = {}
    partial: list[dict] = []
    absent: list[dict] = []
    blocked: list[dict] = []

    for g in GROUPS:
        gdir = src_dir / g
        if not gdir.is_dir():
            blocked.append({"group": g, "reason": "source directory missing"})
            continue
        for run in sorted(os.listdir(gdir)):
            rdir = gdir / run
            if not rdir.is_dir():
                continue
            found_events = False
            for root, dirs, names in os.walk(rdir):
                dirs.sort()
                for name in sorted(names):
                    if name not in NAMES:
                        continue
                    path = Path(root) / name
                    rel = path.relative_to(src_dir)
                    dest = _dest_rel(rel.parts)
                    text, part_lines = _sanitize(_read(path), pairs)
                    written[dest] = text
                    partial.extend({"file": dest, "line": n} for n in part_lines)
                    if name == "events.jsonl":
                        found_events = True
            if not found_events:
                reason, errors = _absent_reason(g, rdir)
                item = {
                    "group": g,
                    "run": run,
                    "file": "events.jsonl",
                    "reason": reason,
                }
                if errors is not None:
                    item["errors"] = errors
                absent.append(item)

    for name in TOP_FILES:
        top = src_dir / name
        if top.is_file():
            text, part_lines = _sanitize(_read(top), pairs)
            written[name] = text
            partial.extend({"file": name, "line": n} for n in part_lines)

    literals = []
    for var in ("OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        val = os.environ.get(var)
        if val and len(val) >= 8:
            literals.append(val)
    hits: list[str] = []
    for rel, text in written.items():
        hits.extend(_key_hits(rel, text, literals))
    if hits:
        shutil.rmtree(dst_dir, ignore_errors=True)
        for h in hits:
            print(f"key scan hit: {h}", file=sys.stderr)
        return 1

    dst_dir.mkdir(parents=True, exist_ok=True)
    for rel in sorted(written):
        out = dst_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as fh:
            fh.write(written[rel])

    manifest = {
        "source": "$TMPDIR/cora-m20",
        "files": sorted(written),
        "absent_at_source": absent,
        "blocked": blocked,
        "key_scan": {"files": len(written), "matches": 0},
        "sanitize": {
            "placeholders": PLACEHOLDERS,
            "partial_tmp": sorted(partial, key=lambda e: (e["file"], e["line"])),
        },
    }
    (dst_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy and sanitize M20 artifacts.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("copy", help="copy sanitized artifacts into --dst")
    c.add_argument("--src", required=True)
    c.add_argument("--dst", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "copy":
        return copy(args.src, args.dst)
    return 2


if __name__ == "__main__":
    sys.exit(main())
