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
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


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


def test_m25_revision1_corrections():
    section = _section()
    assert "plan:underived-selector" in section
    assert "p1c는 29행" in section
    assert "tests.test_normalize" in section
    assert "p1c 21행은" not in section


def test_usage_documents_m25_keys():
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    keys = ("goal_paths", "plan_repair_hint", "tripwire_per_response", "plan_reply_rejected")
    for key in (*keys, "scan_objects"):
        assert key in text
    assert "plan:underived-selector" in text


def test_architecture_documents_m25():
    text = (ROOT / ".docs/architecture.md").read_text(encoding="utf-8")
    keys = ("validate_plan_paths", "plan_reply_rejected", "tripwire_per_response")
    for key in (*keys, "plan:underived-selector"):
        assert key in text


def test_paid_item_recorded():
    section = _section()
    if "### (p)" not in section:
        pytest.skip("M25 item (p) not recorded yet")
    item = section[section.index("### (p)"):]
    assert "deepseek-fix3" in item
    rows = []
    if PLANQ.exists():
        rows = [r for r in _jsonl(PLANQ) if str(r.get("label", "")).startswith("deepseek-fix4")]
    if rows:
        for line in m20_trial.summary(rows, [], None).splitlines():
            if line.startswith("|") or line.startswith("####"):
                assert line in section
        assert "deepseek-fix4-off" in section
        assert "deepseek-fix4-on" in section
    else:
        assert "not run" in item
        assert "이유" in item


@pytest.mark.skipif(not PLANQ.exists(), reason="fix4 planq rows not recorded yet")
def test_fix4_lines():
    rows = _jsonl(PLANQ)
    section = _section()
    for line in m20_trial.summary(rows, [], None).splitlines():
        if line.startswith("|") or line.startswith("####"):
            assert line in section
