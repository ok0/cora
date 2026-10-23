from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cora.core.config import McpServerConfig, McpSettings
from cora.core.toolgroups import MCP_TOOL_PREFIX, mcp_group
from cora.core.tools.base import ToolContext, ToolResult, truncate_text
from cora.core.tools.mcp_client import (
    CLOSE_GRACE_S,
    MAX_MESSAGE_BYTES,
    McpClient,
    McpError,
    McpRpcError,
    McpTimeout,
    child_env,
)

MCP_MAX_OUTPUT_CHARS = 16000
MAX_TOOL_NAME_CHARS = 64
MAX_CONSECUTIVE_FAILURES = 2
MAX_CONSECUTIVE_TIMEOUTS = 2
ERROR_SUMMARY_CHARS = 300
EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
DISABLED, NOT_STARTED, RUNNING, CRASHED, FAILED = (
    "disabled", "not started", "running", "crashed", "failed",
)
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")


def exposed_name(server: str, tool: str) -> str:
    name = f"{MCP_TOOL_PREFIX}{server}__{_UNSAFE.sub('_', tool) or '_'}"
    if len(name) > MAX_TOOL_NAME_CHARS:
        digest = hashlib.sha1(tool.encode("utf-8")).hexdigest()[:8]
        name = f"{name[: MAX_TOOL_NAME_CHARS - 9]}_{digest}"
    return name


def object_schema(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict) and schema.get("type") == "object":
        return schema
    return dict(EMPTY_SCHEMA)


def convert_result(result: dict[str, Any], limit: int) -> ToolResult:
    parts: list[str] = []
    content = result.get("content")
    for item in content if isinstance(content, list) else []:
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(
            item.get("text"), str
        ):
            parts.append(item["text"])
        else:
            kind = item.get("type") if isinstance(item, dict) else None
            parts.append(f"[non-text content omitted: {str(kind or 'unknown')[:40]}]")
    text = "\n".join(parts) or "(no output)"
    if result.get("isError") is True:
        return ToolResult(False, truncate_text(f"MCP tool error: {text}", limit))
    return ToolResult(True, truncate_text(text, limit))


class McpTool:
    requires_approval = True
    read_only = False

    def __init__(self, manager: Any, server: str, tool: str, name: str,
                 description: str, schema: dict[str, Any]) -> None:
        self._manager = manager
        self.server = server
        self.tool = tool
        self.name = name
        self.description = description or f"MCP tool '{tool}' from server '{server}'."
        self.native_description = self.description
        self.parameters = schema
        self.args_doc = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        shown = truncate_text(json.dumps(args, ensure_ascii=False, indent=2), 2000)
        return ToolResult(
            True, f"MCP server '{self.server}', tool '{self.tool}' ({self.name})\n"
                  f"arguments:\n{shown}",
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(self._manager.call_tool, self.server, self.tool, args)


def build_tools(manager: Any, server: str, raw_tools: list[dict[str, Any]]
                ) -> tuple[list[McpTool], list[str]]:
    tools: list[McpTool] = []
    notes: list[str] = []
    owners: dict[str, str] = {}
    for raw in raw_tools:
        tool = raw.get("name")
        if not isinstance(tool, str) or not tool:
            notes.append("skipped a tool without a valid name")
            continue
        name = exposed_name(server, tool)
        if name in owners:
            notes.append(f"skipped tool '{tool[:80]}': name {name} collides with "
                         f"tool '{owners[name][:80]}'")
            continue
        owners[name] = tool
        desc = raw.get("description")
        tools.append(McpTool(manager, server, tool, name, desc if isinstance(desc, str) else "",
                             object_schema(raw.get("inputSchema"))))
    return tools, notes


@dataclass(frozen=True)
class McpServerStatus:
    name: str
    state: str
    tools: tuple[McpTool, ...] = ()
    last_error: str | None = None
    pid: int | None = None
    restarts: int = 0
    notes: tuple[str, ...] = ()


@dataclass(eq=False)
class _Server:
    cfg: McpServerConfig
    state: str
    client: McpClient | None = None
    tools: list[McpTool] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    failures: int = 0
    timeouts: int = 0
    restarts: int = 0
    started: bool = False
    last_error: str | None = None
    lock: Any = field(default_factory=threading.RLock)


def _redact(text: str, cfg: McpServerConfig) -> str:
    for _, value in cfg.env:
        if len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    return text


def _stderr_summary(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][-3:]
    return " | ".join(lines)[-200:]


class McpManager:
    def __init__(self, settings: McpSettings, cwd: Path, *,
                 output_chars: int = MCP_MAX_OUTPUT_CHARS,
                 max_message_bytes: int = MAX_MESSAGE_BYTES,
                 close_grace_s: float = CLOSE_GRACE_S) -> None:
        self._cwd = cwd
        self._output_chars = output_chars
        self._max_message_bytes = max_message_bytes
        self._grace = close_grace_s
        self._lock = threading.Lock()
        self._closed = False
        self._servers: dict[str, _Server] = {}
        for cfg in settings.servers:
            if cfg.error is not None:
                srv = _Server(cfg, FAILED, last_error=cfg.error)
            elif not cfg.enabled:
                srv = _Server(cfg, DISABLED)
            else:
                srv = _Server(cfg, NOT_STARTED)
            self._servers.setdefault(cfg.name, srv)

    def __enter__(self) -> McpManager:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def has_servers(self) -> bool:
        return bool(self._servers)

    def server_names(self) -> list[str]:
        return list(self._servers)

    def usable_servers(self) -> list[str]:
        return [n for n, s in self._servers.items() if s.cfg.error is None and s.cfg.enabled]

    def active_servers(self, disabled_groups: Collection[str]) -> list[str]:
        return [n for n in self.usable_servers()
                if mcp_group(n) not in disabled_groups and self._servers[n].state != FAILED]

    def ensure_tools(self, servers: Iterable[str]) -> list[McpTool]:
        out: list[McpTool] = []
        for name in servers:
            s = self._servers.get(name)
            if s is None or s.cfg.error is not None or not s.cfg.enabled:
                continue
            with s.lock:
                self._check_alive(s)
                if s.state == NOT_STARTED or (s.state == CRASHED and not s.tools):
                    self._start(s)
                if s.state in (RUNNING, CRASHED):
                    out.extend(s.tools)
        return out

    def cached_tools(self) -> list[McpTool]:
        return [t for s in self._servers.values() if s.state in (RUNNING, CRASHED)
                for t in s.tools]

    def probe_all(self) -> list[McpServerStatus]:
        for name in self.usable_servers():
            self.ensure_tools([name])
        return self.statuses()

    def call_tool(self, server: str, tool: str, args: dict[str, Any]) -> ToolResult:
        s = self._servers.get(server)
        if s is None or s.cfg.error is not None or not s.cfg.enabled:
            return ToolResult(False, f"error: MCP server '{server}' is not available")
        with s.lock:
            self._check_alive(s)
            if s.state == FAILED:
                return ToolResult(False, f"error: MCP server '{server}' failed and is not "
                                         f"restarted this session ({s.last_error}). See /mcp.")
            if s.state in (NOT_STARTED, CRASHED) and not self._start(s):
                return ToolResult(False, f"error: MCP server '{server}' could not be started "
                                         f"({s.last_error}). See /mcp.")
            client = s.client
            if client is None:
                return ToolResult(False, f"error: MCP server '{server}' is not running")
            try:
                result = client.call_tool(tool, args, s.cfg.timeout_s)
            except McpTimeout:
                s.timeouts += 1
                if s.timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    self._crash(s, f"unresponsive: {s.timeouts} calls in a row timed out")
                return ToolResult(False, f"error: MCP tool '{tool[:80]}' on server '{server}' "
                                         f"timed out after {s.cfg.timeout_s:g}s")
            except McpRpcError as e:
                s.timeouts = 0
                s.failures = 0
                return ToolResult(False, truncate_text(
                    f"error: MCP server '{server}' returned error {e.code}: {e.message}",
                    self._output_chars))
            except McpError as e:
                self._crash(s, str(e))
                again = ("it will be restarted on the next call" if s.state == CRASHED
                         else "it will not be restarted this session")
                return ToolResult(False, f"error: MCP server '{server}' crashed during "
                                         f"'{tool[:80]}' ({s.last_error}); {again}")
            except Exception as e:
                self._crash(s, f"client error: {type(e).__name__}")
                return ToolResult(False, f"error: MCP call failed ({type(e).__name__})")
            s.timeouts = 0
            s.failures = 0
            return convert_result(result, self._output_chars)

    def statuses(self) -> list[McpServerStatus]:
        out: list[McpServerStatus] = []
        for name, s in self._servers.items():
            state, error = s.state, s.last_error
            if state == RUNNING and s.client is not None and s.client.dead is not None:
                state, error = CRASHED, _redact(f"server stopped: {s.client.dead}", s.cfg)
            pid = s.client.pid if state == RUNNING and s.client is not None else None
            out.append(McpServerStatus(name, state, tuple(s.tools), error, pid, s.restarts,
                                       tuple(s.notes)))
        return out

    def close(self) -> None:
        with self._lock:
            self._closed = True
            clients = [s.client for s in self._servers.values() if s.client is not None]
        for c in clients:
            c.close()

    def _check_alive(self, s: _Server) -> None:
        if s.state == RUNNING and s.client is not None and s.client.dead is not None:
            self._crash(s, f"server stopped: {s.client.dead}")

    def _start(self, s: _Server) -> bool:
        if s.failures >= MAX_CONSECUTIVE_FAILURES:
            s.state = FAILED
            return False
        if s.client is not None:
            s.client.close()
        client = McpClient([s.cfg.command, *s.cfg.args], child_env(dict(s.cfg.env)), self._cwd,
                           max_message_bytes=self._max_message_bytes,
                           close_grace_s=self._grace)
        start_error: McpError | None = None
        with self._lock:
            if self._closed:
                s.last_error = "MCP is shut down"
                return False
            s.client = client
            if s.started:
                s.restarts += 1
            s.started = True
            try:
                client.start()
            except McpError as e:
                start_error = e
        if start_error is not None:
            self._crash(s, f"start failed: {start_error}")
            return False
        try:
            client.initialize(s.cfg.timeout_s)
            raw = client.list_tools(s.cfg.timeout_s)
        except (McpError, McpRpcError) as e:
            self._crash(s, f"start failed: {e}")
            return False
        s.tools, s.notes = build_tools(self, s.cfg.name, raw)
        s.state = RUNNING
        s.timeouts = 0
        return True

    def _crash(self, s: _Server, reason: str) -> None:
        s.failures += 1
        tail = ""
        if s.client is not None:
            s.client.close()
            tail = _stderr_summary(s.client.stderr_tail())
        message = f"{reason}; stderr: {tail}" if tail else reason
        s.last_error = _redact(message, s.cfg)[:ERROR_SUMMARY_CHARS]
        s.state = FAILED if s.failures >= MAX_CONSECUTIVE_FAILURES else CRASHED
