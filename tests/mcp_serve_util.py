from __future__ import annotations

import io
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

from conftest import CFG_TOML
from cora.cli.mcp_serve import R10_KEYS, serve
from cora.core.tools.mcp_client import PROTOCOL_VERSION

ENTRY = Path(__file__).with_name("headless_entry.py")
FAKE_CFG = CFG_TOML.replace('provider = "scripted"', 'provider = "headless_fake"')
DEADLINE = 30


def serve_cfg(
    tmp_path: Path, mcp: str = "", base: str = CFG_TOML, name: str = "serve.toml"
) -> Path:
    path = tmp_path / name
    path.write_text(base + ("\n[mcp]\n" + mcp if mcp else ""), encoding="utf-8")
    return path


def assert_frame(raw: bytes) -> dict:
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    obj = json.loads(raw)
    assert obj["jsonrpc"] == "2.0"
    assert sum(k in obj for k in ("result", "error", "method")) == 1
    return obj


def payload(resp: dict) -> dict:
    return json.loads(resp["result"]["content"][0]["text"])


class _Client:
    _stdin: BinaryIO
    _closed = False

    def __init__(self, stream: BinaryIO) -> None:
        self.raw: list[bytes] = []
        self.notifications: list[dict] = []
        self._q: queue.Queue = queue.Queue()
        self._next = 1
        self._reader = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self._reader.start()

    def _read(self, stream: BinaryIO) -> None:
        try:
            for line in iter(stream.readline, b""):
                self.raw.append(line)
                self._q.put(line)
        except (OSError, ValueError):
            pass
        self._q.put(None)

    def _write(self, data: bytes) -> None:
        self._stdin.write(data)
        self._stdin.flush()

    def send(self, obj: dict) -> None:
        self._write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def send_raw(self, data: bytes) -> None:
        self._write(data)

    def request(self, method: str, params: dict | None = None, rid: Any = None) -> Any:
        if rid is None:
            rid = self._next
            self._next += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        return rid

    def recv(self, timeout: float = 10.0) -> dict:
        try:
            line = self._q.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError("no message within timeout") from None
        assert line is not None, "stream closed"
        return assert_frame(line)

    def wait_response(self, rid: Any, timeout: float = DEADLINE) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            msg = self.recv(timeout=max(deadline - time.monotonic(), 0.01))
            if msg.get("id") == rid and ("result" in msg or "error" in msg):
                return msg
            self.notifications.append(msg)

    def initialize(self) -> dict:
        rid = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        resp = self.wait_response(rid)
        assert "result" in resp
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return resp

    def call(self, name: str, args: dict, *, rid: Any = None, meta: dict | None = None) -> dict:
        params: dict[str, Any] = {"name": name, "arguments": args}
        if meta is not None:
            params["_meta"] = meta
        return self.wait_response(self.request("tools/call", params, rid=rid))

    def doc(self, resp: dict) -> dict:
        assert "result" in resp, resp
        d = payload(resp)
        assert set(R10_KEYS) <= set(d)
        assert resp["result"]["isError"] is (not d["ok"])
        return d

    def no_more(self, timeout: float = 0.5) -> None:
        try:
            line = self._q.get(timeout=timeout)
        except queue.Empty:
            return
        if line is None:
            return
        raise AssertionError(f"unexpected message: {line!r}")


class InProc(_Client):
    def __init__(self, cfg: Path, ws: Path) -> None:
        r_in, w_in = os.pipe()
        r_out, w_out = os.pipe()
        self._server_in = os.fdopen(r_in, "rb")
        self._server_out = os.fdopen(w_out, "wb")
        self._stdin = os.fdopen(w_in, "wb")
        self._client_out = os.fdopen(r_out, "rb")
        self.code: int | None = None
        self._serve_thread = threading.Thread(target=self._run, args=(cfg, ws), daemon=True)
        self._serve_thread.start()
        super().__init__(self._client_out)

    def _run(self, cfg: Path, ws: Path) -> None:
        try:
            self.code = serve(cfg, ws, stdin=self._server_in, stdout=self._server_out)
        finally:
            self._server_in.close()
            self._server_out.close()

    def close(self, timeout: float = 10) -> int:
        if self._closed:
            assert self.code is not None
            return self.code
        self._closed = True
        self._stdin.close()
        self._serve_thread.join(timeout)
        assert not self._serve_thread.is_alive(), "server did not exit after stdin EOF"
        self._reader.join(timeout)
        self._client_out.close()
        assert self.code is not None
        return self.code

    def __enter__(self) -> InProc:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class Proc(_Client):
    def __init__(
        self,
        cfg: Path,
        ws: Path,
        tmp_path: Path,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("OPENROUTER_API_KEY", "CORA_TUI", "CORA_MCP_DEPTH")
        }
        env["HOME"] = str(tmp_path)
        env.update(extra_env or {})
        self.proc = subprocess.Popen(
            [sys.executable, str(ENTRY), "mcp", "serve", "-w", str(ws), "-c", str(cfg)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(tmp_path),
            start_new_session=True,
        )
        self.err: list[bytes] = []
        self._stdin = self.proc.stdin
        self._err_thread = threading.Thread(target=self._read_err, daemon=True)
        self._err_thread.start()
        super().__init__(self.proc.stdout)

    def _read_err(self) -> None:
        for line in iter(self.proc.stderr.readline, b""):
            self.err.append(line)

    def stderr_text(self) -> str:
        return b"".join(self.err).decode("utf-8", "replace")

    def close(self, timeout: float = 10) -> int:
        if self._closed:
            return self.proc.returncode
        self._closed = True
        try:
            self._stdin.close()
        except OSError:
            pass
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill()
            raise AssertionError("server did not exit after stdin EOF") from None
        self._reader.join(timeout)
        self._err_thread.join(timeout)
        return rc

    def _kill(self) -> None:
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except OSError:
            pass
        self.proc.wait(timeout=10)

    def __enter__(self) -> Proc:
        return self

    def __exit__(self, *exc: object) -> None:
        if not self._closed:
            self._closed = True
            if self.proc.poll() is None:
                self._kill()
        self.proc.wait(timeout=10)
        self._err_thread.join(5)


def empty_stdin() -> io.BytesIO:
    return io.BytesIO(b"")
