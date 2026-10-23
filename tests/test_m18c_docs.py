from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m18c() -> None:
    text = _read(USAGE)
    for needle in (
        "--verify-attempts",
        "verify_attempts",
        "check_failed",
        "escalate_on_retry",
        "wall_s",
        "채점기",
        "2~5",
    ):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_architecture_m18c() -> None:
    text = _read(ARCH)
    for needle in (
        "--verify-attempts",
        "cheap→cheap",
        "strong_model",
        "escalation_target",
        "ladder",
        "tests/m19_panel.py",
        "indeterminate",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"
