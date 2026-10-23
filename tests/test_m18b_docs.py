from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m18b() -> None:
    text = _read(USAGE)
    for needle in (
        "[delegation] nudge",
        "DELEGATE_NUDGE",
        "attempts_unparsed",
        "deleg_attempts",
        "deleg_calls",
        "M19",
        "측정한 것이 아닙니다",
    ):
        assert needle in text, needle
    assert "재측정 계획은 없습니다" not in text


def test_architecture_m18b() -> None:
    text = _read(ARCH)
    for needle in (
        "nudge",
        "attempts_unparsed",
        "deleg_attempts",
        "force_delegate_visible",
        "M19",
    ):
        assert needle in text, needle
    assert "재측정 계획 없음" not in text
    assert "재측정 계획은 없습니다" not in text
