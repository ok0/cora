from __future__ import annotations

from pathlib import Path

import pytest

from cora.core.config import ToolSettings, load_config, parse_config
from cora.core.errors import ConfigError

MINIMAL_MODELS = {
    "models": [
        {
            "id": "m",
            "provider": "openrouter",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 1.0,
        }
    ]
}


def test_defaults_and_repo_toml_match() -> None:
    assert parse_config(MINIMAL_MODELS).tools == ToolSettings()
    assert load_config(Path("cora.toml")).tools == ToolSettings()
    assert Path("cora.toml").read_bytes() == Path("src/cora/data/cora.toml").read_bytes()


@pytest.mark.parametrize(
    "tools",
    [
        {"web_timeout_s": 0},
        {"git_max_output_chars": 0},
        {"web_max_redirects": -1},
        {"mention_max_total_chars": 10, "mention_max_file_chars": 20},
        {"bogus": 1},
    ],
)
def test_invalid_tools_section(tools: dict) -> None:
    with pytest.raises(ConfigError, match=r"\[tools\]"):
        parse_config({**MINIMAL_MODELS, "tools": tools})
