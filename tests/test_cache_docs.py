from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"

CACHE_M6 = (
    "[cache]", "prompt_cache", "tool_descriptions", "terse", "compress_observations",
    "compress_chars", "cache = true", "cache_read_usd_per_mtok", "cache_control",
    "[compressed:", "기본값",
)
ARCH_M6 = (
    "G1-6", "cache_control", "prompt_tokens_details.cached_tokens",
    "openrouter-prompt-caching", "terse_description", "compress_observations",
)


def test_usage_documents_cache() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in CACHE_M6:
        assert needle in text, f"missing cache topic: {needle!r}"


def test_architecture_documents_cache() -> None:
    text = ARCH.read_text(encoding="utf-8")
    for needle in ARCH_M6:
        assert needle in text, f"missing cache architecture topic: {needle!r}"


READ_GUARD = ("`list_files`, `search`, `read_file`", "denied: credential file")


def test_usage_documents_read_file_guard() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in READ_GUARD:
        assert needle in text, f"missing read_file guard topic: {needle!r}"
