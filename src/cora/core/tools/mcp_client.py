from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cora import __version__

PROTOCOL_VERSION = "2025-06-18"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
STDERR_TAIL_BYTES = 8192
CLOSE_GRACE_S = 1.0
MAX_LIST_PAGES = 50
ENV_ALLOWLIST = frozenset(
    {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TMPDIR", "TZ"}
)
DEPTH_ENV = "CORA_MCP_DEPTH"


def child_env(
    server_env: Mapping[str, str], parent: Mapping[str, str] | None = None
) -> dict[str, str]:
    source = os.environ if parent is None else parent
    env = {k: v for k, v in source.items() if k in ENV_ALLOWLIST or k.startswith("LC_")}
    env.update(server_env)
    if DEPTH_ENV in source:
        env[DEPTH_ENV] = source[DEPTH_ENV]
    return env


class McpError(Exception):
    """Transport or protocol failure; the connection is unusable."""


class McpTimeout(McpError):
    """No response in time; the server may still be alive."""


class McpRpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class _Pending:
    __slots__ = ("event", "msg", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.msg: dict[str, Any] | None = None
        self.error: str | None = None


class McpClient:
    def __init__(self, argv: Sequence[str], env: Mapping[str, str], cwd: Path, *,
                 max_message_bytes: int = MAX_MESSAGE_BYTES,
                 close_grace_s: float = CLOSE_GRACE_S) -> None:
        self._argv = list(argv)
        self._env = dict(env)
        self._cwd = cwd
        self._max = max_message_bytes
        self._grace = close_grace_s
        self.proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0
        self._closed = False
        self.dead: str | None = None
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc is not None else None

    def start(self) -> None:
        try:
            self.proc = subprocess.Popen(
                self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self._env, cwd=self._cwd, shell=False,
                start_new_session=True, close_fds=True,
            )
        except OSError as e:
            raise McpError(
                f"cannot start '{self._argv[0]}': {e.strerror or type(e).__name__}"
            ) from e
        threading.Thread(target=self._read_stdout, name="mcp-stdout", daemon=True).start()
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="mcp-stderr", daemon=True
        )
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        out = self.proc.stdout
        reason = "server closed stdout (EOF)"
        try:
            while True:
                line = out.readline(self._max + 1)
                if not line:
                    break
                if len(line) > self._max and not line.endswith(b"\n"):
                    reason = f"protocol error: message larger than {self._max} bytes"
                    break
                text = line.strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except ValueError:
                    reason = "protocol error: invalid JSON from server"
                    break
                if not isinstance(msg, dict):
                    reason = "protocol error: message is not a JSON object"
                    break
                self._dispatch(msg)
        except (OSError, ValueError) as e:
            reason = f"read error: {type(e).__name__}"
        self._fail(reason)

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        err = self.proc.stderr
        with contextlib.suppress(OSError, ValueError):
            while chunk := err.read1(4096):
                with self._stderr_lock:
                    self._stderr += chunk
                    if len(self._stderr) > STDERR_TAIL_BYTES:
                        del self._stderr[: len(self._stderr) - STDERR_TAIL_BYTES]

    def stderr_tail(self) -> str:
        with self._stderr_lock:
            return bytes(self._stderr).decode("utf-8", "replace")

    def _dispatch(self, msg: dict[str, Any]) -> None:
        if "method" in msg:
            if "id" in msg:
                reply: dict[str, Any] = {"jsonrpc": "2.0", "id": msg["id"]}
                if msg["method"] == "ping":
                    reply["result"] = {}
                else:
                    reply["error"] = {"code": -32601, "message": "Method not found"}
                with contextlib.suppress(McpError):
                    self._send(reply)
            return
        rid = msg.get("id")
        if not isinstance(rid, int) or isinstance(rid, bool):
            return
        with self._lock:
            pending = self._pending.pop(rid, None)
        if pending is None:
            return
        pending.msg = msg
        pending.event.set()

    def _send(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with self._write_lock:
            try:
                assert self.proc is not None and self.proc.stdin is not None
                fd = self.proc.stdin.fileno()
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
            except (OSError, ValueError) as e:
                raise McpError(f"write to server failed: {type(e).__name__}") from e

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        obj: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            obj["params"] = params
        self._send(obj)

    def request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        pending = _Pending()
        with self._lock:
            if self.dead is not None:
                raise McpError(self.dead)
            self._next_id += 1
            rid = self._next_id
            self._pending[rid] = pending
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        except McpError:
            with self._lock:
                self._pending.pop(rid, None)
            raise
        if not pending.event.wait(timeout):
            with self._lock:
                self._pending.pop(rid, None)
            with contextlib.suppress(McpError):
                self.notify("notifications/cancelled", {"requestId": rid, "reason": "timeout"})
            raise McpTimeout(f"no response to {method} within {timeout:g}s")
        if pending.error is not None:
            raise McpError(pending.error)
        msg = pending.msg or {}
        if "error" in msg:
            err = msg["error"] if isinstance(msg["error"], dict) else {}
            code = err.get("code")
            raise McpRpcError(
                code if isinstance(code, int) else -32603,
                str(err.get("message", "unknown error"))[:500],
            )
        result = msg.get("result")
        if not isinstance(result, dict):
            raise McpError("protocol error: response without a result object")
        return result

    def initialize(self, timeout: float) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
             "clientInfo": {"name": "cora", "version": __version__}},
            timeout,
        )
        self.notify("notifications/initialized")
        return result

    def list_tools(self, timeout: float) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(MAX_LIST_PAGES):
            res = self.request("tools/list", {"cursor": cursor} if cursor else {}, timeout)
            page = res.get("tools", [])
            if not isinstance(page, list):
                raise McpError("protocol error: tools/list result has no tools list")
            tools.extend(t for t in page if isinstance(t, dict))
            nxt = res.get("nextCursor")
            if not isinstance(nxt, str) or not nxt:
                return tools
            if nxt in seen:
                raise McpError("protocol error: tools/list repeated a cursor")
            seen.add(nxt)
            cursor = nxt
        raise McpError(f"protocol error: tools/list returned more than {MAX_LIST_PAGES} pages")

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout)

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self.dead is None:
                self.dead = reason
            final = self.dead
            pending = list(self._pending.values())
            self._pending.clear()
        for p in pending:
            p.error = final
            p.event.set()

    def _signal(self, sig: int) -> None:
        if self.proc is not None:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(self.proc.pid, sig)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._fail("connection closed")
        proc = self.proc
        if proc is None:
            return
        if self._write_lock.acquire(timeout=0.2):
            try:
                with contextlib.suppress(OSError, ValueError):
                    if proc.stdin is not None:
                        proc.stdin.close()
            finally:
                self._write_lock.release()
        try:
            proc.wait(timeout=self._grace)
        except subprocess.TimeoutExpired:
            self._signal(signal.SIGTERM)
            try:
                proc.wait(timeout=self._grace)
            except subprocess.TimeoutExpired:
                self._signal(signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=5)
        self._signal(signal.SIGKILL)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=0.5)
