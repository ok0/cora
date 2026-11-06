from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

import pytest

import m22b_baseline as b
from cora.core.policy import SHELL_ALLOW
from cora.core.toolchains import TOOLCHAINS

PY_PATTERNS = (*TOOLCHAINS["python"].commands, *TOOLCHAINS["python"].file_runs)
PASSING_RULES = ("default:shell", "strict:shell")
PROFILES_DM = ("default", "strict")


def _roundtrip(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _sources() -> dict[str, str]:
    _, new = b.load_jsonl(b.GOLDEN)
    return {rec["command"]: rec["source"] for rec in new}


def _is_a(cmd: str, ws: str, old, new) -> bool:
    return (
        old[0] == "allow"
        and new[0] == "deny"
        and new[1] == "default"
        and "python" not in b.WS_TOOLCHAINS[ws]
        and any(fnmatch.fnmatchcase(cmd, p) for p in PY_PATTERNS)
        and not any(fnmatch.fnmatchcase(cmd, p) for p in SHELL_ALLOW)
    )


def _is_b(cmd: str, ws: str, old, new) -> bool:
    if old[0] != "deny" or old[1] != "default":
        return False
    if new[0] != "allow" or new[1] not in PASSING_RULES:
        return False
    return any(
        cmd in TOOLCHAINS[tid].commands for tid in b.WS_TOOLCHAINS[ws]
    )


@pytest.mark.slow
def test_golden_replays(tmp_path: Path) -> None:
    golden_header, golden_records = b.load_jsonl(b.GOLDEN)
    if golden_header["platform"] != sys.platform:
        pytest.skip(f"golden recorded on {golden_header['platform']}")
    header, records = b.decisions(tmp_path)
    strip = {k: v for k, v in header.items() if k != "generated_from"}
    golden_strip = {k: v for k, v in golden_header.items() if k != "generated_from"}
    assert strip == golden_strip
    assert _roundtrip(records) == golden_records


def test_baseline_diff_is_intended() -> None:
    old_header, old = b.load_jsonl(b.BASELINE)
    new_header, new = b.load_jsonl(b.GOLDEN)
    assert old_header["workspaces"] == new_header["workspaces"]
    assert old_header["modes"] == new_header["modes"]
    assert [r["command"] for r in old] == [r["command"] for r in new]
    assert [r["source"] for r in old] == [r["source"] for r in new]

    sources = _sources()
    rows = b.diff_rows(old, new)
    kinds = {"a": 0, "b": 0}
    for command, ws, mode, before, after in rows:
        assert mode != "confine", (command, ws)
        source = sources[command]
        if source == "inline":
            assert after[0] == "deny", (command, ws, mode)
            continue
        assert source == "corpus", command
        if _is_a(command, ws, before, after):
            kinds["a"] += 1
        elif _is_b(command, ws, before, after):
            kinds["b"] += 1
        else:
            raise AssertionError((command, ws, mode, before, after))

    assert not [r for r in rows if r[1] in ("python", "python-wide")]
    for rec in new:
        if rec["command"] in b.GAP_COMMANDS:
            for ws, modes in rec["ws"].items():
                assert modes["confine"] == next(
                    r["ws"][ws]["confine"] for r in old if r["command"] == rec["command"])
                assert modes["default"][0] == "deny", (rec["command"], ws)
                assert modes["strict"][0] == "deny", (rec["command"], ws)

    a_on_none = [r for r in rows if r[1] == "none" and _is_a(r[0], "none", r[3], r[4])]
    assert a_on_none
    for ws in ("node", "rust", "go", "make"):
        assert any(
            _is_b(r[0], ws, r[3], r[4]) for r in rows if r[1] == ws
        ), ws


def test_inline_never_newly_allowed() -> None:
    _, old = b.load_jsonl(b.BASELINE)
    _, new = b.load_jsonl(b.GOLDEN)
    old_by_cmd = {rec["command"]: rec for rec in old}
    for rec in new:
        if rec["source"] != "inline" and rec["command"] not in b.INLINE:
            continue
        for ws, modes in rec["ws"].items():
            for mode in PROFILES_DM:
                if modes[mode][0] == "allow":
                    assert old_by_cmd[rec["command"]]["ws"][ws][mode] == modes[mode], (
                        rec["command"], ws, mode)
    explicit = ("python -c 1", "node -e 1", "perl -e 1", "deno eval 1")
    for rec in new:
        if rec["command"] in explicit:
            for ws, modes in rec["ws"].items():
                for mode in PROFILES_DM:
                    assert modes[mode][0] == "deny", (rec["command"], ws, mode)

