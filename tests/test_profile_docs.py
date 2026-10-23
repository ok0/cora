from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"

USAGE_M7 = (
    "id@provider", "cost_model", "self_hosted", "catalog", "provider_usage", "unpriced",
    "cost_source", "latency_s", "p50_latency_s", "by_model_provider", "self_hosted_cost_usd",
    "profile",
)
ARCH_M7 = (
    "F2", "id@provider", "cost_model", "self_hosted", "cost_source", "A5", "by_model_provider",
)


def test_usage_documents_profile() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in USAGE_M7:
        assert needle in text, f"missing profile topic: {needle!r}"


def test_architecture_documents_profile() -> None:
    text = ARCH.read_text(encoding="utf-8")
    for needle in ARCH_M7:
        assert needle in text, f"missing profile architecture topic: {needle!r}"
