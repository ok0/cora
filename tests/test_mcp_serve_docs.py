from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCHITECTURE = ROOT / ".docs" / "architecture.md"
USAGE_NEEDLES = (
    "cora mcp serve",
    "run_task",
    "resume_session",
    "list_sessions",
    "max_output_chars",
    "max_depth",
    "CORA_MCP_DEPTH",
    "notifications/cancelled",
    "notifications/progress",
    "progressToken",
    ".mcp.json",
    "mcpServers",
    "isError",
    "truncated",
    "busy",
    "2025-06-18",
)


def test_usage_documents_mcp_serve() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in USAGE_NEEDLES:
        assert needle in text, f"missing MCP server topic: {needle!r}"


def test_architecture_mentions_server() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "mcp_serve.py" in text
    assert "CORA_MCP_DEPTH" in text
