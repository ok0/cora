from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CFG_TOML
from cora.core.config import McpServeSettings, load_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]


def _load_snippet(tmp_path: Path, snippet: str):
    path = tmp_path / "cora.toml"
    path.write_text(CFG_TOML + "\n[mcp]\n" + snippet + "\n", encoding="utf-8")
    return load_config(path)


def test_defaults_match_toml():
    assert load_config(ROOT / "cora.toml").mcp.serve == McpServeSettings()
    assert load_config(ROOT / "src/cora/data/cora.toml").mcp.serve == McpServeSettings()
    s = McpServeSettings()
    assert (
        s.max_cost_usd,
        s.max_iterations,
        s.max_wall_s,
        s.max_tool_calls,
        s.max_depth,
        s.max_output_chars,
        s.approval,
    ) == (0.5, 30, 600.0, 200, 1, 20000, "policy")


def test_serve_keys_no_unknown_key_warning(tmp_path):
    cfg = _load_snippet(tmp_path, "max_depth = 2")
    assert cfg.mcp.serve.max_depth == 2
    assert cfg.mcp.warnings == ()


@pytest.mark.parametrize(
    ("snippet", "key"),
    [
        ("max_cost_usd = 0", "max_cost_usd"),
        ("max_cost_usd = -1", "max_cost_usd"),
        ("max_iterations = 0", "max_iterations"),
        ('max_iterations = "3"', "max_iterations"),
        ("max_iterations = true", "max_iterations"),
        ("max_wall_s = 0", "max_wall_s"),
        ("max_tool_calls = 0", "max_tool_calls"),
        ("max_depth = 0", "max_depth"),
        ("max_output_chars = 999", "max_output_chars"),
        ("max_output_chars = 50000", "max_output_chars"),
        ('approval = "auto"', "approval"),
        ('approval = "ask"', "approval"),
    ],
)
def test_invalid_serve_values(tmp_path, snippet, key):
    with pytest.raises(ConfigError, match=rf"invalid \[mcp\]\.{key}"):
        _load_snippet(tmp_path, snippet)


def test_unknown_mcp_key_still_warns(tmp_path):
    cfg = _load_snippet(tmp_path, "foo = 1")
    assert "warning: unknown key [mcp].foo ignored" in cfg.mcp.warnings
    assert cfg.mcp.serve == McpServeSettings()
