from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"

RECORD_M11 = (
    "[record]", "CORA_RECORD_MODE", "CORA_RECORD_DIR", "ReplayMissError", "+replay",
    "tests/fixtures/recordings", "<WS>", "<HOME>", "<TS>", "재녹화",
)
ARCH_M11 = (
    "recording.py", "RecordingProvider", "ReplayMissError", "+replay", "sha256",
    "provider_workspace",
)


def test_usage_documents_record() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in RECORD_M11:
        assert needle in text, f"missing record topic: {needle!r}"


def test_architecture_documents_record() -> None:
    text = ARCH.read_text(encoding="utf-8")
    for needle in ARCH_M11:
        assert needle in text, f"missing record architecture topic: {needle!r}"
