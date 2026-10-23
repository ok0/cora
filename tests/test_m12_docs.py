from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH = ROOT / ".docs" / "bench-results.md"
OLD_STRONG_LINE = "strong 모델은 `moonshotai/kimi-k2-0905`"


def test_usage_documents_m12() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in (
        "deepseek/deepseek-v3.2",
        "OPENROUTER_API_KEY",
        "lenient_parse",
        "parse_repaired",
        "4개 신호 중 3개 이상",
        "실험적",
        "0건",
        "M16",
    ):
        assert needle in text, needle
    assert OLD_STRONG_LINE not in text


def test_architecture_documents_m12() -> None:
    text = ARCH.read_text(encoding="utf-8")
    for needle in (
        "parse_repaired",
        "lenient_parse",
        "deepseek/deepseek-v3.2",
        ".ensemble/research/strong-tier-model.md",
        "0.14",
        "실험적",
        "core/sale.py",
    ):
        assert needle in text, needle
    assert "SALE-lite 1단계" not in text


def test_bench_results_document_m12_router_table() -> None:
    text = BENCH.read_text(encoding="utf-8")
    assert "M12 라우터 점수 재조정" in text
    row = (
        "| written_plugin_system | written | complex | 1 1 1 1 | 8 | complex/strong "
        "| 4 | complex/strong |"
    )
    assert row in text
