from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs/bench-results.md"
RESULT_RE = re.compile(r"^## M20b 결과 \(\d{4}-\d{2}-\d{2}[^)]*\)$", re.M)


def _section() -> str:
    text = BENCH.read_text(encoding="utf-8")
    matches = list(RESULT_RE.finditer(text))
    assert len(matches) == 1
    start = matches[0].start()
    nxt = re.search(r"^## ", text[matches[0].end():], re.M)
    end = matches[0].end() + nxt.start() if nxt else len(text)
    return text[start:end]


def test_usage_documents_m20b() -> None:
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    assert "prompt_rules" in text
    assert "Hint:" in text


def test_architecture_documents_m20b() -> None:
    text = (ROOT / ".docs/architecture.md").read_text(encoding="utf-8")
    assert "deny_observation" in text
    assert "prompt_rules" in text
    assert "M20b" in text


def test_bench_results_m20b_section() -> None:
    section = _section()
    for token in (
        "e2e_h03",
        "e2e_n08",
        "free_tier",
        "non-G1",
        "prompt_rules",
        "n = 2",
        "sensor_gate_slugify",
    ):
        assert token in section, token
