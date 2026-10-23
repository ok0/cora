from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from cora.core.config import McpServerConfig, McpSettings
from cora.core.tools.mcp import McpManager

FAKE = Path(__file__).with_name("fake_mcp_server.py")


def server_cfg(
    name: str,
    log: Path,
    *extra: str,
    mode: str = "normal",
    timeout_s: float = 5.0,
    env: dict[str, str] | None = None,
    enabled: bool = True,
) -> McpServerConfig:
    return McpServerConfig(
        name=name,
        command=sys.executable,
        args=(str(FAKE), "--mode", mode, "--log", str(log), *extra),
        env=tuple(sorted((env or {}).items())),
        enabled=enabled,
        timeout_s=timeout_s,
    )


def make_manager(cwd: Path, *cfgs: McpServerConfig, **kw: Any) -> McpManager:
    return McpManager(McpSettings(tuple(cfgs)), cwd, **kw)


def events(log: Path) -> list[dict]:
    if not Path(log).exists():
        return []
    text = Path(log).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def starts(log: Path) -> list[int]:
    return [e["pid"] for e in events(log) if e.get("event") == "start"]


def tool_calls(log: Path) -> list[str]:
    return [
        e["name"]
        for e in events(log)
        if e.get("event") == "request" and e.get("method") == "tools/call"
    ]


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def toml_server(name: str, log: Path, mode: str = "normal", extra: str = "") -> str:
    args = [str(FAKE), "--mode", mode, "--log", str(log)]
    return (
        f"\n[mcp.servers.{name}]\ncommand = {json.dumps(sys.executable)}\n"
        f"args = {json.dumps(args)}\n" + extra
    )
