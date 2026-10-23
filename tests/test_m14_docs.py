from __future__ import annotations

import re
from pathlib import Path

from m15_sheet import ENTRIES, render

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
SHEET = ROOT / ".docs" / "m15-command-sheet.md"
READINESS = ROOT / ".docs" / "m15-readiness.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"

SHEET_TOPICS = (
    "0.26", "0.38", "0.209", "0.31", "0.10", "0.40", "k_s", "2.6", "0.95",
    "openrouter-prices-followup.md", "rehearsed by replay",
)
READINESS_TOPICS = (
    "total_cost_usd", "modelUsage", "--max-budget-usd", "--output-format json", "--bare",
    "ANTHROPIC_API_KEY", "costBasis", "usage.cost", "cached_tokens", "require_parameters",
    "403", "/auth/key", "Haiku 5.5",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m14() -> None:
    text = _read(USAGE)
    assert "--e2e-task-cost" in text
    assert "require_parameters" in text


def test_architecture_m14() -> None:
    text = _read(ARCH)
    for needle in (
        "--e2e-task-cost", "require_parameters", "auto_check_command_e2e",
        "google/gemini-2.5-flash-lite",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_command_sheet_lists_entries() -> None:
    text = _read(SHEET)
    for e in ENTRIES:
        assert render(e) in text, f"command line missing for {e.id}"
        assert f"{e.estimate_usd:.6f}" in text, f"estimate missing for {e.id}"
    for needle in SHEET_TOPICS:
        assert needle in text, f"missing command sheet topic: {needle!r}"


def test_readiness_note() -> None:
    text = _read(READINESS)
    for needle in READINESS_TOPICS:
        assert needle in text, f"missing readiness topic: {needle!r}"
    assert re.search(r"baseline[^\n]*\$\d", text) is None


def test_bench_results_m14_section() -> None:
    text = _read(BENCH_RESULTS)
    assert "## M14" in text
    assert "$0.50" in text
