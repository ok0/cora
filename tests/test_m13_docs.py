from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCHITECTURE = ROOT / ".docs" / "architecture.md"


def test_usage_documents_m13() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for term in (
        "auto_check",
        "tamper_guard",
        "selftest",
        "ladder",
        "--sensor-source",
        "tests_modified",
        "ladder_exhausted",
        ".cora/selftest",
        "no_check_tasks",
    ):
        assert term in text, term


def test_architecture_documents_m13() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for term in (
        "core/checks.py",
        "detect_check_command",
        "tests_modified",
        ".cora/selftest",
        "ladder_exhausted",
        "ladder = true",
    ):
        assert term in text, term
