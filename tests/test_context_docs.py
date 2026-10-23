from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"

CONTEXT_M5 = (
    "[context]", "repo_map", "repo_map_max_chars", "max_files", "dedupe_reads",
    ".cora/index/repomap.json", "[superseded:", "기본값",
)


def test_usage_documents_context() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in CONTEXT_M5:
        assert needle in text, f"missing context topic: {needle!r}"
