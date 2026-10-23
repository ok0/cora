from __future__ import annotations

import copy
import re
import tomllib
from pathlib import Path

import pytest

from conftest import run_repl
from cora.core.config import McpServerConfig, McpSettings, load_config, parse_config
from cora.core.errors import ConfigError
from cora.core.tools.mcp_client import McpClient

ROOT = Path(__file__).resolve().parents[1]

BASE: dict = {
    "models": [
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
    ],
    "agent": {"approval": "auto"},
}


def _cfg(extra: dict) -> dict:
    data = copy.deepcopy(BASE)
    data.update(copy.deepcopy(extra))
    return data


def test_default_config_has_no_servers_and_files_identical():
    assert (ROOT / "cora.toml").read_bytes() == (ROOT / "src/cora/data/cora.toml").read_bytes()
    assert load_config(ROOT / "cora.toml").mcp == McpSettings()
    assert load_config(ROOT / "src/cora/data/cora.toml").mcp == McpSettings()


def test_no_server_config_never_spawns(scripted, ws, cfg_file, monkeypatch):
    started: list[object] = []

    def boom(self):
        started.append(self)
        raise AssertionError("MCP server started")

    monkeypatch.setattr(McpClient, "start", boom)
    scripted.script.append("Final Answer: ok")
    out = run_repl(ws, cfg_file, ["hello", "/mcp", "/exit"])
    assert started == []
    assert "No MCP servers configured" in out


def test_valid_server_defaults():
    cfg = parse_config(_cfg({"mcp": {"servers": {"x": {"command": "srv"}}}}))
    assert cfg.mcp.servers == (McpServerConfig("x", "srv", (), (), True, 30.0),)
    assert cfg.mcp.warnings == ()


def test_invalid_servers_isolated():
    servers = {
        "good": {"command": "a", "args": ["1"], "env": {"K": "v"}, "timeout_s": 2},
        "nocmd": {},
        "zero": {"command": "a", "timeout_s": 0},
        "bad name!": {"command": "a"},
        "badtype": {"command": "a", "args": "x"},
        "extra": {"command": "a", "arg": []},
        "dbl__x": {"command": "a"},
    }
    cfg = parse_config(_cfg({"mcp": {"servers": servers}}))
    by_name = {s.name: s for s in cfg.mcp.servers}
    assert by_name["good"].error is None
    assert by_name["good"].timeout_s == 2.0
    bad = ["nocmd", "zero", "bad name!", "badtype", "extra", "dbl__x"]
    for name in bad:
        assert name in by_name[name].error
        assert by_name[name].enabled is False
    assert len(cfg.mcp.warnings) == 6
    for name in bad:
        assert sum(name in w for w in cfg.mcp.warnings) == 1
    assert "'command' is required" in by_name["nocmd"].error
    assert "timeout_s" in by_name["zero"].error


def test_env_value_not_in_repr():
    assert "v-secret" not in repr(McpServerConfig("x", "a", env=(("K", "v-secret"),)))


def test_tool_groups_accept_mcp_group():
    cfg = parse_config(_cfg({"tool_groups": {"disabled": ["mcp:x"]}}))
    assert "mcp:x" in cfg.tool_groups.disabled
    with pytest.raises(ConfigError):
        parse_config(_cfg({"tool_groups": {"disabled": ["mcp:bad name"]}}))


def test_no_new_runtime_dependencies():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = {re.split(r">=", dep)[0].strip() for dep in data["project"]["dependencies"]}
    assert names == {"httpx", "typer", "prompt_toolkit", "rich"}
