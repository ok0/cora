from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m16() -> None:
    text = _read(USAGE)
    for needle in (
        "[escalation]",
        "on_stuck_iterations",
        "on_tripwire",
        "on_budget_fraction",
        "strong_model",
        "cheap_first",
        "ladder_exhausted",
        "budget_fraction",
        "escalate",
        "기본값",
    ):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_architecture_m16() -> None:
    text = _read(ARCH)
    for needle in (
        "## M16",
        "core/escalation.py",
        "EscalationPolicy",
        "cheap_first",
        "escalated_at_check",
        "escalation_target",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_bench_results_m16() -> None:
    text = _read(BENCH_RESULTS)
    if "## M16" not in text:
        pytest.skip("M16 live section pending")
    for needle in ("## M16", "solved-per-dollar", "Wilson"):
        assert needle in text, f"missing bench-results topic: {needle!r}"
    assert (
        "reflection effect not measured" in text or "ablation" in text
    ), "missing R18 ablation statement"
