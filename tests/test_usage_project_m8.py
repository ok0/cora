from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
PLANNING_AND_GATE = (
    "cora project plan", "--goal", "conditions", "file_exists", "gate_retries", "gate_failed",
    "failed_condition", "max_milestones", "condition_timeout_s", "condition_output_chars",
    "[project]", "milestone_count",
)


def test_usage_documents_planning_and_gate() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in PLANNING_AND_GATE:
        assert needle in text, f"missing M8 topic: {needle!r}"


def test_architecture_mentions_m8() -> None:
    text = ARCH.read_text(encoding="utf-8")
    assert "core/planner.py" in text
    assert "gate_failed" in text
