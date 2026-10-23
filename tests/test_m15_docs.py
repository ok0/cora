from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"
BASELINE = ROOT / ".docs" / "baseline-protocol.md"

BASELINE_TOPICS = (
    "total_cost_usd", "modelUsage", "--max-budget-usd", "--model", "--output-format json",
    "--bare", "ANTHROPIC_API_KEY", "session_id", "wall", "costBasis", "dry-run", "partial",
    "n=3", "--strict-mcp-config", "CLAUDE.md", "m15-readiness.md", "tests/m15_baseline.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_baseline_protocol() -> None:
    text = _read(BASELINE)
    for needle in BASELINE_TOPICS:
        assert needle in text, f"missing baseline protocol topic: {needle!r}"
    assert re.search(r"\$\d+\.\d+\s*(per|/)\s*task", text) is None


def test_bench_results_m15() -> None:
    text = _read(BENCH_RESULTS)
    for needle in (
        "## M15", "not recorded in M14", "not G1 evidence", "R1-a", "R1-b", "k_s",
        "blocked", "누계",
    ):
        assert needle in text, f"missing bench-results topic: {needle!r}"


def test_architecture_m15() -> None:
    text = _read(ARCH)
    for needle in ("lenient_plan_json", "extract_object", "m15_tables.py", "m15_baseline.py"):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_usage_m15() -> None:
    text = _read(USAGE)
    for needle in ("extract_object", "ask_resolved_deny"):
        assert needle in text, f"missing usage topic: {needle!r}"
