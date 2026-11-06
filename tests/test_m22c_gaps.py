from __future__ import annotations

import copy
import re

import pytest

import m22_golden
import m22b_baseline as b
import m22c_baseline as cb
import m22c_cases as c
from cora.core.policy import RULE_HINTS
from cora.core.shellguard import INTERPRETERS, interpreter_for


@pytest.fixture(scope="module")
def evaluator(tmp_path_factory):
    return m22_golden.Evaluator(tmp_path_factory.mktemp("m22c"))


def _regex(template: str) -> re.Pattern[str]:
    pieces = re.split(r"(\{\w+\})", template)
    body = "".join(".*" if re.fullmatch(r"\{\w+\}", p) else re.escape(p) for p in pieces)
    return re.compile(body, re.S)


def _reason_patterns(rule: str) -> list[re.Pattern[str]]:
    templates = [
        template
        for spec in INTERPRETERS.values()
        for rule_id, template in spec.messages.values()
        if rule_id == rule
    ]
    templates += [
        "{what} without a script file is not allowed",
        "{what} would run code read from a pipe",
    ]
    return [_regex(t) for t in templates]


def _before(cmd: str) -> dict:
    _, snap = cb.load_snapshot()
    return next(s["record"] for s in snap if s["golden"] == "m22" and s["command"] == cmd)


@pytest.mark.parametrize("profile", ["confine", "default", "strict"])
@pytest.mark.parametrize("cmd", list(c.GAP_FORMS))
def test_gap_form_denied(evaluator, cmd, profile):
    v = evaluator.record(cmd)[profile]
    assert v[0] == "deny"
    assert v[1] == c.GAP_FORMS[cmd]
    assert v[2] == evaluator.record(c.CLOSED_FORM[cmd])["confine"][2]


@pytest.mark.parametrize("cmd", [k for k in c.EXPECTED if k not in c.GAP_FORMS])
def test_variant_behaves_like_closed_form(evaluator, cmd):
    rec = evaluator.record(cmd)
    expected = c.EXPECTED[cmd]
    if expected == "=":
        before = _before(cmd)
        for mode in m22_golden.MODES:
            assert rec[mode] == before[mode], (cmd, mode)
        return
    assert rec["confine"][0] == "deny"
    assert rec["confine"][1] == expected
    assert any(p.fullmatch(rec["confine"][2]) for p in _reason_patterns(expected)), (
        cmd, rec["confine"][2])
    for mode in ("default", "strict"):
        assert rec[mode][0] == "deny", (cmd, mode)
        assert rec[mode][1] == rec["confine"][1], (cmd, mode)


def test_cases_in_both_goldens():
    _, m22 = m22_golden.load_golden()
    _, m22b = b.load_jsonl(b.GOLDEN)
    m22_by_cmd = {r["command"]: r for r in m22}
    m22b_cmds = {r["command"] for r in m22b}
    assert set(c.ALL) <= set(m22_by_cmd)
    for cmd in c.ALL:
        names = [seg["argv"][0].rsplit("/", 1)[-1] for seg in m22_by_cmd[cmd]["analyze"]["segments"]
                 if seg["argv"]]
        if any(interpreter_for(n) is not None for n in names):
            assert cmd in m22b_cmds, cmd


def test_golden_diff_is_gap_only():
    rows, violations = cb.golden_diff()
    assert violations == []
    for cmd in c.GAP_FORMS:
        assert any(
            r[0] == "m22" and r[1] == cmd and r[2] == "confine"
            and r[3][0] == "allow" and r[4][0] == "deny"
            for r in rows
        ), cmd
        assert any(
            r[0] == "m22b" and r[1] == cmd and r[2] == "none/confine"
            and r[3][0] == "allow" and r[4][0] == "deny"
            for r in rows
        ), cmd


def test_diff_checker_rejects_outside_change(monkeypatch):
    real = cb.current()
    cur = {golden: [dict(r) for r in recs] for golden, recs in real.items()}
    for i, rec in enumerate(cur["m22"]):
        if rec["command"] == "ls":
            changed = copy.deepcopy(rec)
            changed["confine"] = [
                changed["confine"][0], changed["confine"][1],
                changed["confine"][2] + " (changed)", changed["confine"][3],
            ]
            cur["m22"][i] = changed
            break
    monkeypatch.setattr(cb, "current", lambda: cur)
    _, violations = cb.golden_diff()
    assert any(v.startswith("m22: ls ") for v in violations), violations


def test_diff_checker_rejects_gap_regression(monkeypatch):
    header, snap = cb.load_snapshot()
    cur = cb.current()
    cmd = "perl -pe x README.md"
    snap = [dict(s) for s in snap]
    for s in snap:
        if s["golden"] == "m22" and s["command"] == cmd:
            s["record"] = copy.deepcopy(s["record"])
            s["record"]["confine"] = ["deny", c.GAP_FORMS[cmd], "x", False]
            s["sha256"] = "x"
    cur = {golden: [dict(r) for r in recs] for golden, recs in cur.items()}
    for i, rec in enumerate(cur["m22"]):
        if rec["command"] == cmd:
            changed = copy.deepcopy(rec)
            changed["confine"] = ["allow", "confine:ok", "x", False]
            cur["m22"][i] = changed
    monkeypatch.setattr(cb, "load_snapshot", lambda: (header, snap))
    monkeypatch.setattr(cb, "current", lambda: cur)
    _, violations = cb.golden_diff()
    assert any(f"m22: {cmd} [confine]" in v for v in violations), violations


def test_no_new_rule_ids():
    for rule in {r for r in c.EXPECTED.values() if r != "="}:
        assert rule in c.GAP_RULES, rule
    for rule in c.GAP_RULES - {"floor:pipe-exec"}:
        assert rule in RULE_HINTS, rule
