from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import m20_trial

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs/bench-results.md"
PLANQ = ROOT / "tests" / "fixtures" / "m20a" / "planq.jsonl"
M20A_RE = re.compile(r"^## M20a 결과 \(\d{4}-\d{2}-\d{2}\)$", re.M)


def _m20a_section() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = M20A_RE.search(text)
    assert m is not None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def _planq_rows() -> list[dict]:
    rows: list[dict] = []
    for line in PLANQ.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_fix3_lines_in_section() -> None:
    if not PLANQ.is_file():
        pytest.skip("m20a planq fixture is absent")
    section = _m20a_section()
    out = m20_trial.summary(_planq_rows(), [], None)
    lines = [ln for ln in out.splitlines() if ln.startswith("|") or ln.startswith("####")]
    assert lines
    for ln in lines:
        assert ln in section, ln
    assert "ungated milestones" in section
    assert "deepseek-fix3" in section or "not measured" in section


def test_m20a_spend() -> None:
    if not PLANQ.is_file():
        return
    total = sum(
        float(r["cost_usd"])
        for r in _planq_rows()
        if str(r.get("label", "")).startswith("deepseek")
    )
    assert total <= 0.05
