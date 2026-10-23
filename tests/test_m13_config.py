from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML
from cora.cli.main import app
from cora.core.config import AgentSettings, load_config, parse_config
from cora.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
TOMLS = [ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml"]
NEW_KEYS = ("auto_check", "tamper_guard", "selftest", "ladder")
MODELS = [
    {
        "id": "mock/cheap",
        "provider": "scripted",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    },
    {
        "id": "mock/strong",
        "provider": "scripted",
        "tier": "strong",
        "input_usd_per_mtok": 5.0,
        "output_usd_per_mtok": 10.0,
    },
]


def write_cfg(tmp_path: Path, text: str, name: str = "cora.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def base(ws: Path, cfg: Path) -> list[str]:
    return ["-w", str(ws), "-c", str(cfg)]


@pytest.mark.parametrize("path", TOMLS, ids=["repo", "packaged"])
def test_new_keys_off_in_shipped_tomls(path: Path) -> None:
    agent = load_config(path).agent
    for key in NEW_KEYS:
        assert getattr(agent, key) is False
    text = path.read_text(encoding="utf-8")
    section = text.split("[agent]", 1)[1].split("\n[", 1)[0]
    for key in NEW_KEYS:
        assert f"{key} = false" in section
    assert TOMLS[0].read_bytes() == TOMLS[1].read_bytes()


def test_new_keys_default_false() -> None:
    agent = AgentSettings()
    for key in NEW_KEYS:
        assert getattr(agent, key) is False


@pytest.mark.parametrize("key", NEW_KEYS)
def test_invalid_new_keys(key: str) -> None:
    with pytest.raises(ConfigError, match=rf"\[agent\]\.{key}"):
        parse_config({"models": MODELS, "agent": {key: "yes"}})


@pytest.mark.parametrize("key", NEW_KEYS)
def test_invalid_new_key_exit_2(tmp_path: Path, ws: Path, key: str) -> None:
    cfg = write_cfg(tmp_path, CFG_TOML + f"\n[agent]\n{key} = \"yes\"\n")
    result = CliRunner().invoke(app, ["run", "q", "--headless", *base(ws, cfg)])
    assert result.exit_code == 2
    assert "error: invalid [agent]." in result.stderr
