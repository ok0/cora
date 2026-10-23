from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
BENCH_RESULTS = ROOT / ".docs" / "bench-results.md"

GATE_KEYS = ("verify_before_final", "compile_check", "edge_case_prompt", "stub_check")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_m16c() -> None:
    text = _read(USAGE)
    for needle in (
        "call_timeout_s",
        "provider_timeout",
        *GATE_KEYS,
        "gate_feedback",
        "기본값",
    ):
        assert needle in text, f"missing usage topic: {needle!r}"


def test_arch_m16c() -> None:
    text = _read(ARCH)
    for needle in (
        "call_timeout_s",
        "provider_timeout",
        "finalgate",
        *GATE_KEYS,
    ):
        assert needle in text, f"missing architecture topic: {needle!r}"


def test_recipe_m16c() -> None:
    text = _read(BENCH_RESULTS)
    for needle in ("M16c 준비", "arm_a.toml", "arm_e.toml", "--max-cost 0.30"):
        assert needle in text, f"missing recipe item: {needle!r}"
    for key in GATE_KEYS:
        assert f"{key} = true" in text, f"missing recipe key: {key} = true"
