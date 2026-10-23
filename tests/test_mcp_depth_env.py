from __future__ import annotations

from pathlib import Path

from cora.core.shellguard import clean_env
from cora.core.tools.mcp_client import child_env


def test_child_env_passes_depth() -> None:
    assert child_env({}, {"CORA_MCP_DEPTH": "1", "PATH": "/bin", "SECRET_X": "s"}) == {
        "PATH": "/bin",
        "CORA_MCP_DEPTH": "1",
    }


def test_child_env_depth_not_overridable() -> None:
    assert child_env({"CORA_MCP_DEPTH": "0"}, {"CORA_MCP_DEPTH": "2"})["CORA_MCP_DEPTH"] == "2"


def test_child_env_without_depth() -> None:
    assert "CORA_MCP_DEPTH" not in child_env({}, {"PATH": "/bin"})


def test_clean_env_passes_depth(tmp_path: Path) -> None:
    assert clean_env({"CORA_MCP_DEPTH": "1", "PATH": "/bin"}, tmp_path)["CORA_MCP_DEPTH"] == "1"
