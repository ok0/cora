from __future__ import annotations

import json

import pytest

import m20_trial
from m20_trial import ROOT

FIX = ROOT / "tests/fixtures/m25"
DOCS = ROOT / ".docs/bench-results.md"
PLANQ = FIX / "planq.jsonl"
M25_HEADING = "## M25 결과 ("


def _section() -> str:
    text = DOCS.read_text(encoding="utf-8")
    start = text.index(M25_HEADING)
    return text[start:]


def _jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_m25_section_and_order():
    text = DOCS.read_text(encoding="utf-8")
    assert M25_HEADING in text
    assert text.index(M25_HEADING) > text.index("## M21 결과 (")
    section = _section()
    assert "blocked" in section
    assert "원인 순위" in section


def test_m25_section_rows():
    section = _section()
    for row in _jsonl(FIX / "refcheck_classes.jsonl"):
        assert row["milestone"] in section
        assert row["class"] in section
    for row in _jsonl(FIX / "denials.jsonl"):
        assert row["cite"] in section


@pytest.mark.skipif(not PLANQ.exists(), reason="fix4 planq rows not recorded yet")
def test_fix4_lines():
    rows = _jsonl(PLANQ)
    section = _section()
    for line in m20_trial.summary(rows, [], None).splitlines():
        if line.startswith("|") or line.startswith("####"):
            assert line in section
