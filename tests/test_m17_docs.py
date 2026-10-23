from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m17() -> None:
    text = _read(USAGE)
    for needle in (
        "ledger_max_chars",
        "summarize",
        "ledger_update",
        "ledger_evict_note",
        "summary_call",
        '"llm"',
    ):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_arch_m17() -> None:
    text = _read(ARCH)
    for needle in (
        "WorkingStateLedger",
        "ledger_max_chars",
        "summarize",
        "ledger_update",
        "ledger_evict_note",
        "summary_call",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"
