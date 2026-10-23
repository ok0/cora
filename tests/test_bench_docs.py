from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"
ROADMAP = ROOT / ".docs" / "roadmap.md"
TEMPLATE_HEADING = "## Bench v2 결과 템플릿 (실측 전 비어 있음)"
NUMBER_PATTERNS = (r"\d+/\d+", r"\$\d", r"\d\.\d")
LIVE_ITEMS = ("| G1-1 ", "| G1-2 ", "| G2-1 ")


def _section(text: str, heading: str) -> str:
    start = text.index(heading) + len(heading)
    match = re.search(r"^## ", text[start:], re.M)
    return text[start:] if match is None else text[start : start + match.start()]


def test_bench_results_template_has_no_measured_numbers() -> None:
    text = BENCH_RESULTS.read_text(encoding="utf-8")
    assert TEMPLATE_HEADING in text
    section = _section(text, TEMPLATE_HEADING)
    assert "실측 전 비어 있음" in section
    for pattern in NUMBER_PATTERNS:
        assert re.search(pattern, section) is None, pattern


def test_roadmap_marks_live_items_as_needing_credits() -> None:
    lines = ROADMAP.read_text(encoding="utf-8").splitlines()
    for prefix in LIVE_ITEMS:
        rows = [ln for ln in lines if ln.startswith(prefix)]
        assert rows, prefix
        assert all("크레딧 필요" in ln for ln in rows), prefix
