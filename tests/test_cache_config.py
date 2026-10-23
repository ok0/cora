from __future__ import annotations

import filecmp
import tomllib
from pathlib import Path

import pytest

from cora.core.config import (
    CacheSettings,
    ModelOverride,
    apply_model_override,
    load_config,
    parse_config,
)
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
MODEL = {
    "id": "mock/cheap",
    "provider": "openrouter",
    "tier": "cheap",
    "input_usd_per_mtok": 0.2,
    "output_usd_per_mtok": 0.8,
}


def test_defaults():
    assert CacheSettings() == CacheSettings(False, "full", False, 800)
    assert load_config(ROOT / "cora.toml").cache == CacheSettings()
    assert filecmp.cmp(ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml", shallow=False)
    data = tomllib.loads((ROOT / "cora.toml").read_text(encoding="utf-8"))
    assert data["cache"] == {
        "prompt_cache": False,
        "tool_descriptions": "full",
        "compress_observations": False,
        "compress_chars": 800,
    }
    for m in load_config(ROOT / "cora.toml").models:
        assert m.cache is False
        assert m.cache_read_usd_per_mtok == (0.028 if m.id == "deepseek/deepseek-v3.2" else None)


def test_model_cache_keys():
    cfg = parse_config({"models": [{**MODEL, "cache": True, "cache_read_usd_per_mtok": 0.3}]})
    assert cfg.models[0].cache is True
    assert cfg.models[0].cache_read_usd_per_mtok == 0.3
    plain = parse_config({"models": [MODEL]})
    assert plain.models[0].cache is False
    assert plain.models[0].cache_read_usd_per_mtok is None


@pytest.mark.parametrize(
    "section",
    [
        {"cache": "x"},
        {"cache": {"prompt_cache": "yes"}},
        {"cache": {"compress_observations": 1}},
        {"cache": {"tool_descriptions": "short"}},
        {"cache": {"compress_chars": 0}},
        {"cache": {"compress_chars": -5}},
        {"cache": {"compress_chars": True}},
        {"cache": {"compress_chars": "800"}},
        {"cache": {"bogus": 1}},
    ],
)
def test_invalid_cache_values(section):
    with pytest.raises(ConfigError):
        parse_config({"models": [MODEL], **section})


def test_invalid_model_cache_values():
    with pytest.raises(ConfigError):
        parse_config({"models": [{**MODEL, "cache": "yes"}]})
    with pytest.raises(ConfigError):
        parse_config({"models": [{**MODEL, "cache_read_usd_per_mtok": -1}]})


def test_override_keeps_cache_flag():
    cfg = parse_config({"models": [{**MODEL, "cache": True}]})
    out = apply_model_override(cfg, ModelOverride("cheap", "mock/cheap"), "user")
    assert out.models[0].cache is True
