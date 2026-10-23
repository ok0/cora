from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m15b() -> None:
    text = _read(USAGE)
    for needle in ("write_file", "delete_file", "react_max_tokens", "default:delete"):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_architecture_m15b() -> None:
    text = _read(ARCH)
    for needle in (
        "M15b", "react_max_tokens", "reply_truncated", "TRUNCATED_ERROR",
        "_unclosed_input", "FINAL_RE",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_bench_results_m15b() -> None:
    text = _read(BENCH_RESULTS)
    for needle in ("## M15b", "query_env_override", "M18", "M17"):
        assert needle in text, f"missing bench-results topic: {needle!r}"
