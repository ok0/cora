from __future__ import annotations

import os

import m22_golden
import m22b_baseline as b
import m22c_baseline as cb
import m22c_cases as c
from cora.core import shellguard


def _variant_commands() -> list[str]:
    return [cmd for family in c.VARIANTS.values() for cmd in family]


def _control_commands() -> list[str]:
    return [cmd for family in c.CONTROLS.values() for cmd in family]


def _snapshot_m22() -> dict[str, dict]:
    _, snap = cb.load_snapshot()
    return {s["command"]: s["record"] for s in snap if s["golden"] == "m22" and "record" in s}


def test_cases_disjoint_and_unique() -> None:
    flat = _variant_commands() + _control_commands() + list(c.ROUTED)
    assert len(flat) == len(set(flat))
    assert c.GAP_FAMILY & c.PINNED == set()
    assert set(c.EXPECTED) == c.GAP_FAMILY
    assert set(c.EXPECTED.values()) <= c.GAP_RULES | {"="}


def test_cases_in_goldens() -> None:
    m22 = {r["command"]: r for r in m22_golden.load_golden()[1]}
    assert set(c.ALL) <= set(m22)
    m22b = {r["command"] for r in b.load_jsonl(b.GOLDEN)[1]}
    for cmd in c.ALL:
        argv0s = [
            os.path.basename(seg["argv"][0])
            for seg in m22[cmd]["analyze"]["segments"]
            if seg["argv"]
        ]
        if any(shellguard.interpreter_for(name) is not None for name in argv0s):
            assert cmd in m22b, cmd


def test_snapshot_holds_cases() -> None:
    _, snap = cb.load_snapshot()
    by = {(s["golden"], s["command"]): s for s in snap}
    for cmd in c.ALL:
        assert ("m22", cmd) in by and "record" in by[("m22", cmd)], cmd


def test_gap_forms_allowed_today() -> None:
    recs = _snapshot_m22()
    for cmd in c.GAP_FORMS:
        assert recs[cmd]["confine"][:2] == ["allow", "confine:ok"], cmd


def test_pinned_reproduce_today(tmp_path) -> None:
    evaluator = m22_golden.Evaluator(tmp_path)
    recs = _snapshot_m22()
    for cmd in sorted(c.PINNED):
        expected = {k: v for k, v in recs[cmd].items() if k != "command"}
        assert cb.strip(evaluator.record(cmd)) == expected, cmd
