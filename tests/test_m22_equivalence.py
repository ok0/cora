from __future__ import annotations

import sys

import pytest

import m22_golden

HEADER, RECORDS = m22_golden.load_golden()


@pytest.fixture(scope="module")
def evaluator(tmp_path_factory):
    return m22_golden.Evaluator(tmp_path_factory.mktemp("m22"))


def test_golden_header():
    assert HEADER["total"] == len(RECORDS)
    blocked_sources = " ".join(entry["source"] for entry in HEADER["blocked"])
    for cat in ("tests", "adversarial", "m20", "m20d", "generated"):
        assert HEADER["categories"].get(cat, 0) > 0 or cat in blocked_sources
    assert HEADER["modes"] == list(m22_golden.MODES)


def test_golden_holds_adversarial():
    commands = {r["command"] for r in RECORDS}
    for command in m22_golden._adversarial():
        assert command in commands


def test_decision_equivalence(evaluator):
    if HEADER["platform"] != sys.platform:
        pytest.skip(f"golden recorded on {HEADER['platform']}, running on {sys.platform}")
    diffs: list[str] = []
    for rec in RECORDS:
        actual = evaluator.record(rec["command"])
        for key in ("analyze", *m22_golden.MODES):
            if actual[key] != rec[key]:
                diffs.append(
                    f"{rec['command']!r} [{key}]\n  expected: {rec[key]}\n  actual:   {actual[key]}"
                )
    assert not diffs, f"{len(diffs)} differences\n" + "\n".join(diffs[:20])
