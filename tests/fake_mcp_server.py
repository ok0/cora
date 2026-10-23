from __future__ import annotations

import json
import os
import signal
import sys
import time

PAGE_SIZE = 6

TOOLS: list[dict] = [
    {
        "name": "echo",
        "description": "Echo the text argument.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "mixed",
        "description": "Return text, an image and more text.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "readonly",
        "description": "Looks read-only.",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "integer"}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "fail",
        "description": "Return an isError result.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "rpc_error",
        "description": "Return a JSON-RPC error.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "slow",
        "description": "Sleep before answering.",
        "inputSchema": {"type": "object", "properties": {"seconds": {"type": "number"}}},
    },
    {
        "name": "big",
        "description": "Return a large text.",
        "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}},
    },
    {
        "name": "env",
        "description": "Return the server environment.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "crash",
        "description": "Crash the server.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "badjson",
        "description": "Print invalid JSON.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hugeline",
        "description": "Print one huge line.",
        "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}},
    },
    {
        "name": "weird.name/x",
        "description": "Name needs sanitizing.",
        "inputSchema": "not-an-object",
    },
]


def _opt(argv: list[str], name: str, default: str | None) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def log_event(path: str | None, **event: object) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(rid: object, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": payload}


def text_result(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def call_tool(rid: object, name: str, args: dict, log: str | None) -> None:
    if name == "echo":
        send(result(rid, text_result(str(args.get("text", "")))))
    elif name == "mixed":
        send(
            result(
                rid,
                {
                    "content": [
                        {"type": "text", "text": "before"},
                        {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"},
                        {"type": "text", "text": "after"},
                    ]
                },
            )
        )
    elif name == "readonly":
        send(result(rid, text_result("readonly ran")))
    elif name == "fail":
        send(
            result(
                rid,
                {
                    "content": [{"type": "text", "text": "something went wrong"}],
                    "isError": True,
                },
            )
        )
    elif name == "rpc_error":
        send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32602, "message": "bad params for rpc_error"},
            }
        )
    elif name == "slow":
        time.sleep(float(args.get("seconds", 5)))
        send(result(rid, text_result("slow done")))
    elif name == "big":
        send(result(rid, text_result("x" * int(args.get("n", 50000)))))
    elif name == "env":
        send(result(rid, text_result(json.dumps(dict(os.environ)))))
    elif name == "crash":
        sys.stderr.write("crashing during call\n")
        sys.stderr.flush()
        os._exit(3)
    elif name == "badjson":
        sys.stdout.write("{not json\n")
        sys.stdout.flush()
    elif name == "hugeline":
        sys.stdout.write("a" * int(args.get("n", 200000)) + "\n")
        sys.stdout.flush()
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "unknown tool"}})


def handle(msg: dict, mode: str, log: str | None) -> None:
    method = msg.get("method")
    if method is None:
        log_event(log, event="client_reply", msg=msg)
        return
    params = msg.get("params") or {}
    log_event(
        log,
        event="request",
        method=method,
        name=params.get("name"),
        cursor=params.get("cursor"),
    )
    rid = msg.get("id")
    if method == "initialize":
        if mode == "badjson_on_start":
            sys.stdout.write("this is not json\n")
            sys.stdout.flush()
            return
        send(
            result(
                rid,
                {
                    "protocolVersion": params.get("protocolVersion"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1.0"},
                },
            )
        )
    elif method == "notifications/initialized":
        send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/message",
                "params": {"level": "info", "data": "hello"},
            }
        )
        send({"jsonrpc": "2.0", "id": "srv-1", "method": "roots/list"})
    elif method == "tools/list":
        cursor = params.get("cursor")
        start = PAGE_SIZE if cursor == "page2" else 0
        payload: dict = {"tools": TOOLS[start : start + PAGE_SIZE]}
        if start == 0:
            payload["nextCursor"] = "page2"
        send(result(rid, payload))
    elif method == "tools/call":
        args = params.get("arguments") or {}
        call_tool(rid, str(params.get("name")), args, log)
    elif rid is not None:
        send(
            {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}
        )


def main() -> None:
    argv = sys.argv[1:]
    mode = _opt(argv, "--mode", "normal") or "normal"
    log = _opt(argv, "--log", None)
    env_var = _opt(argv, "--env-var", None) or ""
    log_event(log, event="start", pid=os.getpid(), argv=argv)
    if mode == "crash_on_start":
        sys.stderr.write("boom: crashing on start\n")
        sys.stderr.flush()
        sys.exit(1)
    if mode == "stderr_env":
        sys.stderr.write(f"value={os.environ.get(env_var, '')}\n")
        sys.stderr.flush()
        sys.exit(1)
    if mode == "ignore_stdin":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if isinstance(msg, dict):
            handle(msg, mode, log)
    if mode == "ignore_stdin":
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
