"""M22c baseline: pre-change snapshot of the M22 and M22b goldens for the gap cases.

Usage (from the project root):
    uv run python tests/m22c_baseline.py snapshot --write
    uv run python tests/m22c_baseline.py snapshot --check
    uv run python tests/m22c_baseline.py table
    uv run python tests/m22c_baseline.py diff
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import m22_golden
import m22b_baseline as b
import m22c_cases as c

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests/fixtures/m22c/before.jsonl"
GOLDENS = ("m22", "m22b")


def strip(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "sources"}


def record_sha(rec: dict) -> str:
    text = json.dumps(strip(rec), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _dump(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def current() -> dict[str, list[dict]]:
    return {"m22": m22_golden.load_golden()[1], "m22b": b.load_jsonl(b.GOLDEN)[1]}


def snapshot_lines() -> list[str]:
    cur = current()
    header = {
        "kind": "header",
        "generated_from": m22_golden._git_head(),
        "m22_total": len(cur["m22"]),
        "m22b_total": len(cur["m22b"]),
    }
    lines = [_dump(header)]
    for golden in GOLDENS:
        for rec in cur[golden]:
            line: dict = {"golden": golden, "command": rec["command"], "sha256": record_sha(rec)}
            if rec["command"] in c.ALL:
                line["record"] = strip(rec)
            lines.append(_dump(line))
    return lines


def load_snapshot() -> tuple[dict, list[dict]]:
    lines = [line for line in SNAPSHOT.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def transition_ok(before: list, after: list) -> bool:
    return (
        after[0] == "deny"
        and after[1] in c.GAP_RULES
        and (before[0] == "allow" or before[1] == "default")
    )


def _slots(golden: str, before_rec: dict, after_rec: dict) -> list[tuple[str, list, list]]:
    if golden == "m22":
        return [(mode, before_rec[mode], after_rec[mode]) for mode in m22_golden.MODES]
    out: list[tuple[str, list, list]] = []
    for ws, modes in after_rec["ws"].items():
        for mode in b.MODES:
            out.append((f"{ws}/{mode}", before_rec["ws"][ws][mode], modes[mode]))
    return out


def golden_diff() -> tuple[list[tuple[str, str, str, list, list]], list[str]]:
    _, snap = load_snapshot()
    cur = current()
    rows: list[tuple[str, str, str, list, list]] = []
    violations: list[str] = []
    for golden in GOLDENS:
        old_cmds = [s["command"] for s in snap if s["golden"] == golden]
        new_cmds = [r["command"] for r in cur[golden]]
        if old_cmds != new_cmds:
            violations.append(f"{golden}: command list differs from snapshot")
    before_by = {(s["golden"], s["command"]): s for s in snap}
    for golden in GOLDENS:
        for rec in cur[golden]:
            cmd = rec["command"]
            prev = before_by.get((golden, cmd))
            if prev is None or prev["sha256"] == record_sha(rec):
                continue
            if cmd not in c.GAP_FAMILY:
                violations.append(f"{golden}: {cmd} changed outside the gap family")
                continue
            for slot, before, after in _slots(golden, prev["record"], rec):
                if before == after:
                    continue
                rows.append((golden, cmd, slot, before, after))
                if not transition_ok(before, after):
                    violations.append(
                        f"{golden}: {cmd} [{slot}] {before} -> {after} is not a gap closure"
                    )
                if c.EXPECTED[cmd] == "=":
                    violations.append(f"{golden}: {cmd} [{slot}] changed but expected =")
    return rows, violations


def _esc(text: str) -> str:
    return text.replace("|", "\\|")


def _cell(v: list) -> str:
    return _esc(f"{v[0]} {v[1]} — {v[2]}")


def _short(v: list) -> str:
    return _esc(f"{v[0]} {v[1]}")


def _m22_records() -> dict[str, dict]:
    _, snap = load_snapshot()
    return {s["command"]: s["record"] for s in snap if s["golden"] == "m22" and "record" in s}


def _row(kind: str, cmd: str, intended: str, recs: dict[str, dict]) -> str:
    rec = recs[cmd]
    return (
        f"| {kind} | {_esc(cmd)} | {_cell(rec['confine'])} | {_cell(rec['default'])} "
        f"| {_cell(rec['strict'])} | {_esc(intended)} |"
    )


def table() -> int:
    recs = _m22_records()
    print("| kind | command | confine | default | strict | intended |")
    print("| --- | --- | --- | --- | --- | --- |")
    for cmd in c.GAP_FORMS:
        print(_row("gap", cmd, f"deny {c.EXPECTED[cmd]}", recs))
    for cmds in c.CONTROLS.values():
        for cmd in cmds:
            print(_row("control", cmd, "= today", recs))
    for cmd, reason in c.ROUTED.items():
        print(_row("routed", cmd, f"= today (A4: {reason})", recs))
    print()
    for family, variants in c.VARIANTS.items():
        counts = Counter(variants.values())
        detail = ", ".join(f"{rule}: {n}" for rule, n in counts.items())
        print(f"variants {family}: {len(variants)} total ({detail})")
    return 0


def diff() -> int:
    rows, violations = golden_diff()
    print("| golden | command | mode | before | after |")
    print("| --- | --- | --- | --- | --- |")
    for golden, cmd, mode, before, after in rows:
        if golden == "m22":
            print(f"| m22 | {_esc(cmd)} | {mode} | {_short(before)} | {_short(after)} |")
    print()
    print("| golden | command | mode | before | after | workspaces |")
    print("| --- | --- | --- | --- | --- | --- |")
    all_ws = set(b.WS_FILES)
    groups: dict[tuple[str, str, str, str], list[str]] = {}
    for golden, cmd, slot, before, after in rows:
        if golden != "m22b":
            continue
        ws, mode = slot.rsplit("/", 1)
        groups.setdefault((cmd, mode, _short(before), _short(after)), []).append(ws)
    for (cmd, mode, before, after), wss in groups.items():
        listed = "all" if set(wss) == all_ws else ", ".join(wss)
        print(f"| m22b | {_esc(cmd)} | {mode} | {before} | {after} | {listed} |")
    print()
    if violations:
        print("violations:")
        for item in violations:
            print(f"- {item}")
        return 1
    print("violations: none")
    return 0


def _write() -> int:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text("\n".join(snapshot_lines()) + "\n", encoding="utf-8")
    print("ok: snapshot written")
    return 0


def _check() -> int:
    _, old = load_snapshot()
    new = [json.loads(line) for line in snapshot_lines()[1:]]
    old_lines = [_dump(r) for r in old]
    new_lines = [_dump(r) for r in new]
    if old_lines == new_lines:
        print(f"ok: {len(new)} lines match")
        return 0
    old_set, new_set = set(old_lines), set(new_lines)
    diffs = sorted(
        {r["command"] for r in new if _dump(r) not in old_set}
        | {r["command"] for r in old if _dump(r) not in new_set}
    )
    print(f"snapshot differs: golden={len(old)} fresh={len(new)}")
    for cmd in diffs[:20]:
        print(cmd)
    if not diffs:
        print("order differs")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M22c baseline snapshot and golden diff")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_snap = sub.add_parser("snapshot")
    group = p_snap.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    sub.add_parser("table")
    sub.add_parser("diff")
    args = parser.parse_args(argv)
    if args.cmd == "table":
        return table()
    if args.cmd == "diff":
        return diff()
    if args.write:
        return _write()
    return _check()


if __name__ == "__main__":
    sys.exit(main())
