from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE_NEEDLES = (
    "[decider]",
    "/decider",
    "cora decider eval",
    "`--decider`",
    "`--cases`",
    "min_confidence",
    "max_cost_per_decision",
    "resolved-per-dollar",
    "오케스트레이터",
    "Jev",
    "typesafe/jev-router",
    "fallback",
)
ARCH_NEEDLES = (
    "Decider",
    "fallback",
    "pin",
    "force_tier",
    "결정적 센서",
    "resolved-per-dollar",
    "오케스트레이터",
    "Jev",
    "typesafe/jev-router",
    "core/decider.py",
)


def test_usage_documents_decider() -> None:
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for needle in USAGE_NEEDLES:
        assert needle in text, f"USAGE.md missing {needle!r}"


def test_architecture_documents_decider() -> None:
    text = (ROOT / ".docs" / "architecture.md").read_text(encoding="utf-8")
    for needle in ARCH_NEEDLES:
        assert needle in text, f"architecture.md missing {needle!r}"
