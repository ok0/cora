from __future__ import annotations

from pathlib import Path

import pytest

from cora.bench.live import _arm_config
from cora.core.config import load_config
from cora.core.router import HeuristicRouter

ROOT = Path(__file__).resolve().parents[1]
GEMINI = "google/gemini-2.5-flash-lite"
TOMLS = [ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml"]


def test_default_tomls_identical() -> None:
    assert TOMLS[0].read_bytes() == TOMLS[1].read_bytes()


@pytest.mark.parametrize("path", TOMLS, ids=["repo", "packaged"])
def test_default_cheap_model(path: Path) -> None:
    cfg = load_config(path)
    router = HeuristicRouter(cfg)
    cheap = router.resolve("cheap")
    assert (
        cheap.id,
        cheap.provider,
        cheap.tier,
        cheap.input_usd_per_mtok,
        cheap.output_usd_per_mtok,
        cheap.context_tokens,
        cheap.supports_tools,
    ) == (GEMINI, "openrouter", "cheap", 0.10, 0.40, 1048576, True)
    assert HeuristicRouter(cfg).route("What is 2+2?").model.id == GEMINI
    ids = [m.id for m in cfg.models]
    assert "qwen/qwen3-coder-30b-a3b-instruct" in ids
    assert "mistralai/mistral-small-3.2-24b-instruct" in ids
    assert router.resolve("strong").id == "deepseek/deepseek-v3.2"
    assert cfg.bench.models[0] == GEMINI


@pytest.mark.parametrize("path", TOMLS, ids=["repo", "packaged"])
def test_default_strong_model(path: Path) -> None:
    cfg = load_config(path)
    strong = HeuristicRouter(cfg).resolve("strong")
    assert strong.provider == "openrouter"
    assert strong.tier == "strong"
    assert (
        strong.input_usd_per_mtok,
        strong.output_usd_per_mtok,
        strong.cache_read_usd_per_mtok,
    ) == (0.28, 0.42, 0.028)
    assert [m.id for m in cfg.models if m.tier == "strong"] == ["deepseek/deepseek-v3.2"]
    kimi = next(m for m in cfg.models if m.id == "moonshotai/kimi-k2-0905")
    assert kimi.tier != "strong"


def test_ab_reorder_when_bench_model_already_first() -> None:
    cfg = load_config(ROOT / "cora.toml")
    r = HeuristicRouter(cfg)
    out = _arm_config(
        cfg, "auto-routed", r.resolve("cheap"), r.resolve("strong"), "react", 4, 0.05,
        ("core",), False,
    )
    assert HeuristicRouter(out).resolve("cheap").id == GEMINI
    assert out.router.pin is None


def test_docs_cite_default_model_evidence() -> None:
    usage = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for needle in (GEMINI, "방향성", "재검증"):
        assert needle in usage, needle
    bench = (ROOT / ".docs" / "bench-results.md").read_text(encoding="utf-8")
    for needle in (
        "11/11", "$0.00144", "7/11", "3/11", "35~62", "150~190", "19 tok/s",
        "방향성 증거", "재검증",
    ):
        assert needle in bench, needle
