from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
RESULTS = ROOT / ".docs" / "bench-results.md"

RESULT_HEADINGS = ("## M21 사전 등록", "## M21 리허설", "## M21 결과")
VERDICT_LINES = ("L:", "S:", "M:", "D:", "C:")


def test_m21_docs() -> None:
    assert "M21" in USAGE.read_text(encoding="utf-8"), "USAGE.md has no M21 text"
    assert "M21" in ARCH.read_text(encoding="utf-8"), "architecture.md has no M21 text"

    results = RESULTS.read_text(encoding="utf-8")
    for heading in RESULT_HEADINGS:
        assert heading in results, f"missing bench-results heading: {heading!r}"

    start = results.index("## M21 결과")
    section = results[start:]
    for verdict in VERDICT_LINES:
        assert verdict in section, f"missing verdict line: {verdict!r}"
    assert "비-G1" in section, "result section lacks 비-G1 label"
