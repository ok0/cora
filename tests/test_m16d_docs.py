from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"

M16D_KEYS = (
    "verify_before_final",
    "compile_check",
    "edge_case_prompt",
    "stub_check",
    "json_string_repair",
    "overwrite_guard",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m16d() -> None:
    text = _read(USAGE)
    for needle in (
        "json_string_repair",
        "overwrite_guard",
        "overwrite_refused",
        "json_strings",
        "기본값",
    ):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_arch_m16d() -> None:
    text = _read(ARCH)
    for needle in (
        "json_string_repair",
        "overwrite_guard",
        "OverwriteGuard",
        "overwrite_refused",
        "json_strings",
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_recipe_m16d() -> None:
    text = _read(BENCH_RESULTS)
    for needle in (
        "M16d 사전 등록 판정 규칙",
        "12/18",
        "22.1",
        "FINAL STOP",
        "M16d 준비",
        "arm_a2.toml",
        "--max-cost 0.30",
        "--seed 3",
    ):
        assert needle in text, f"missing recipe item: {needle!r}"
    for key in M16D_KEYS:
        assert f"{key} = true" in text, f"missing recipe key: {key} = true"
