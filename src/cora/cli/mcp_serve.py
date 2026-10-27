from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from cora import __version__
from cora.cli.common import force_delegate_visible, load_resolved, unpriced_warnings
from cora.core.agent import Agent
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.config import CoraConfig, McpServeSettings, find_config
from cora.core.errors import CoraError, describe_provider_error
from cora.core.metering import CostMeter
from cora.core.outcome import error_outcome, outcome_dict, session_totals
from cora.core.policy import POLICY_MODE_NOTICE
from cora.core.project import load_project_context
from cora.core.state import SessionStore
from cora.core.tools import ApprovalPolicy
from cora.core.tools.mcp import McpManager
from cora.core.tools.mcp_client import DEPTH_ENV, MAX_MESSAGE_BYTES, PROTOCOL_VERSION

SUPPORTED_VERSIONS = (PROTOCOL_VERSION,)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
LIST_DEFAULT = 20
LIST_MAX = 100
EXCERPT_CHARS = 120
PROGRESS_INTERVAL_S = 1.0
PROGRESS_EVENTS = frozenset({"llm_call", "tool_call"})
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_clock = time.monotonic
_progress_clock = time.monotonic
BUDGET_ARGS = {
    "max_cost_usd": ("cost_usd", float),
    "max_iterations": ("iterations", int),
    "max_wall_s": ("wall_s", float),
    "max_tool_calls": ("tool_calls", int),
}
R10_KEYS = (
    "ok",
    "stop_reason",
    "final_answer",
    "session_id",
    "cost_usd",
    "iterations",
    "tokens",
    "wall_s",
    "budget",
    "policy",
    "warnings",
    "truncated",
)
TRUNC_MARKER = "\n...[truncated: {n} more chars; full answer stored in session {sid}]"
BUSY_MSG = (
    "busy: another run_task/resume_session is in progress (one run at a time); "
    "retry after it finishes"
)

_BUDGET_SCHEMA = {
    "max_cost_usd": {
        "type": "number",
        "minimum": 0,
        "description": "USD cap for this call; 0 or absent = server ceiling; "
        "values above the ceiling are clamped",
    },
    "max_iterations": {
        "type": "integer",
        "minimum": 0,
        "description": "model call cap for this call; 0 or absent = server ceiling; "
        "values above the ceiling are clamped",
    },
    "max_wall_s": {
        "type": "number",
        "minimum": 0,
        "description": "wall-clock seconds for this call; 0 or absent = server ceiling; "
        "values above the ceiling are clamped",
    },
    "max_tool_calls": {
        "type": "integer",
        "minimum": 0,
        "description": "tool call cap for this call; 0 or absent = server ceiling; "
        "values above the ceiling are clamped",
    },
}

TOOLS: list[dict] = [
    {
        "name": "run_task",
        "description": "Run a CORA agent task synchronously and return one JSON text block "
        "(ok, stop_reason, final_answer, session_id, cost_usd, iterations, tokens, wall_s, "
        "budget, policy, warnings, truncated). isError is true when ok is false. Refused "
        "when CORA_MCP_DEPTH reaches [mcp] max_depth (recursion guard). Keep max_wall_s "
        "small, below the MCP client tool timeout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "minLength": 1, "description": "the task text"},
                **_BUDGET_SCHEMA,
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resume_session",
        "description": "Continue a stored CORA session by session_id (see list_sessions). "
        "An optional task adds a follow-up request. Synchronous; returns the same JSON as "
        "run_task. Budget caps are cumulative across the session. Refused inside a served "
        "run when CORA_MCP_DEPTH reaches [mcp] max_depth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "id from list_sessions"},
                "task": {"type": "string", "minLength": 1, "description": "optional follow-up"},
                **_BUDGET_SCHEMA,
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_sessions",
        "description": "List stored CORA sessions in this workspace, newest first. Returns one "
        "JSON text block with session_id, created_at, updated_at, task excerpt, stop_reason "
        "and cost_usd per session. Does not start a run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "default 20, capped at 100",
                },
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]
TOOL_NAMES = frozenset(t["name"] for t in TOOLS)
_TOOL_PROPS = {
    "run_task": ("task", *BUDGET_ARGS),
    "resume_session": ("session_id", "task", *BUDGET_ARGS),
    "list_sessions": ("limit",),
}
_TOOL_REQUIRED = {"run_task": ("task",), "resume_session": ("session_id",), "list_sessions": ()}


class InvalidParams(Exception):
    pass


@dataclass
class _Run:
    req_id: str | int
    token: str | int | None
    thread: threading.Thread | None = None
    agent: Agent | None = None
    cancelled: bool = False
    done: bool = False
    last_progress: float | None = None
    progress_n: int = 0


def parse_depth(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return 0
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def _budget_value(key: str, value: Any) -> int | float:
    kind = BUDGET_ARGS[key][1]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidParams(f"{key} must be a number >= 0")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidParams(f"{key} must be a number >= 0")
    if value < 0:
        raise InvalidParams(f"{key} must be a number >= 0")
    if kind is int:
        if isinstance(value, float):
            if not value.is_integer():
                raise InvalidParams(f"{key} must be an integer >= 0")
            return int(value)
        return value
    return float(value)


def validate_args(tool: str, args: Any) -> dict:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise InvalidParams("arguments must be an object")
    for key in args:
        if key not in _TOOL_PROPS[tool]:
            raise InvalidParams(f"unknown argument: {key}")
    for key in _TOOL_REQUIRED[tool]:
        if key not in args:
            raise InvalidParams(f"missing argument: {key}")
    out = dict(args)
    if "task" in args:
        task = args["task"]
        if not isinstance(task, str) or not task.strip():
            raise InvalidParams("task must be a non-empty string")
        out["task"] = task.strip()
    if "session_id" in args:
        sid = args["session_id"]
        if not isinstance(sid, str) or SESSION_ID_RE.fullmatch(sid) is None:
            raise InvalidParams("session_id must be a stored session id (see list_sessions)")
    for key in BUDGET_ARGS:
        if key in args:
            out[key] = _budget_value(key, args[key])
    if tool == "list_sessions":
        limit = args.get("limit", LIST_DEFAULT)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise InvalidParams("limit must be an integer >= 1")
        out["limit"] = min(limit, LIST_MAX)
    return out


def clamp_limits(args: dict, s: McpServeSettings) -> BudgetLimits:
    ceilings = {
        "max_cost_usd": s.max_cost_usd,
        "max_iterations": s.max_iterations,
        "max_wall_s": s.max_wall_s,
        "max_tool_calls": s.max_tool_calls,
    }
    values: dict[str, Any] = {}
    for arg, (field, kind) in BUDGET_ARGS.items():
        ceiling = ceilings[arg]
        req = args.get(arg)
        value = ceiling if req is None or req == 0 else min(kind(req), ceiling)
        values[field] = kind(value)
    return BudgetLimits(**values)


def _text_len(d: dict) -> int:
    return len(json.dumps(d, ensure_ascii=False))


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


def fit_result(doc: dict, cap: int) -> dict:
    d = {**doc, "truncated": False}
    if _text_len(d) <= cap:
        return d
    d["truncated"] = True
    policy = d.get("policy")
    if isinstance(policy, dict) and "decisions" in policy:
        pol = {k: v for k, v in policy.items() if k != "decisions"}
        pol["decisions_omitted"] = len(policy["decisions"])
        d["policy"] = pol
    for key in ("warnings", "errors"):
        if isinstance(d.get(key), list):
            d[key] = [str(x)[:300] for x in d[key][:10]]
    prof = d.get("profile")
    if isinstance(prof, list) and prof and _text_len(d) > cap:
        d["profile"] = []
        d["profile_omitted"] = len(prof)
    if _text_len(d) <= cap:
        return d
    answer = d.get("final_answer")
    if isinstance(answer, str) and answer:
        sid = d.get("session_id")

        def candidate(k: int) -> dict:
            marker = TRUNC_MARKER.format(n=len(answer) - k, sid=sid)
            return {**d, "final_answer": answer[:k] + marker}

        lo, hi, best = 0, len(answer), 0
        while lo <= hi:
            mid = (lo + hi) // 2
            if _text_len(candidate(mid)) <= cap:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        d = candidate(best)
    return d


def _excerpt(task: str) -> str:
    return _clip(" ".join(task.split()), EXCERPT_CHARS)


def list_sessions_doc(workdir: Path, limit: int, cap: int) -> dict:
    store = SessionStore(workdir / ".cora" / "sessions")
    sessions = []
    for sid in store.list_ids():
        try:
            sessions.append(store.load(sid))
        except (CoraError, OSError, ValueError, TypeError, KeyError):
            continue
    sessions.sort(key=lambda s: (s.created_at, s.id), reverse=True)
    entries = [
        {
            "session_id": s.id,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "task": _excerpt(s.task),
            "stop_reason": s.stop_reason,
            "cost_usd": CostMeter.from_list(s.meter).summary(s.delegation_stats)["total_cost_usd"],
        }
        for s in sessions[:limit]
    ]
    doc = {
        "ok": True,
        "sessions": entries,
        "count": len(entries),
        "total": len(sessions),
        "cost_usd": 0.0,
        "truncated": False,
    }
    while _text_len(doc) > cap and doc["sessions"]:
        doc["sessions"].pop()
        doc["count"] = len(doc["sessions"])
        doc["truncated"] = True
    return doc


def tool_result(doc: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(doc, ensure_ascii=False)}],
        "isError": not doc["ok"],
    }


def _reject_doc(message: str, stop_reason: str) -> dict:
    return {**error_outcome(message, 1, stop_reason=stop_reason), "truncated": False}


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _id_of(msg: Any) -> str | int | None:
    if isinstance(msg, dict) and _valid_id(msg.get("id")):
        return msg["id"]
    return None


class McpServer:
    def __init__(
        self,
        cfg: CoraConfig,
        workdir: Path,
        out: BinaryIO,
        *,
        depth: int | None,
        depth_raw: str,
        warnings: list[str],
    ) -> None:
        self.cfg = cfg
        self.workdir = workdir
        self.out = out
        self.depth = depth
        self.depth_raw = depth_raw
        self.warnings = list(warnings)
        self.settings = cfg.mcp.serve
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._run: _Run | None = None
        self._closed = False

    def _send(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8", "replace"
        )
        with self._write_lock:
            if self._closed:
                return
            try:
                self.out.write(data)
                self.out.flush()
            except OSError:
                self._closed = True

    def _reply(self, rid: str | int | None, result: dict) -> None:
        self._send({"jsonrpc": "2.0", "id": rid, "result": result})

    def _error(self, rid: str | int | None, code: int, message: str) -> None:
        self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})

    def handle_line(self, line: bytes) -> None:
        text = line.strip()
        if not text:
            return
        try:
            msg = json.loads(text.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as e:
            self._error(None, PARSE_ERROR, f"parse error: {e}")
            return
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self._error(_id_of(msg), INVALID_REQUEST, "invalid request")
            return
        if "method" not in msg:
            return
        is_request = "id" in msg
        if is_request and not _valid_id(msg["id"]):
            self._error(None, INVALID_REQUEST, "invalid request")
            return
        try:
            self._dispatch(msg, is_request)
        except Exception as e:
            print(f"cora mcp serve: internal error: {type(e).__name__}: {e}", file=sys.stderr)
            if is_request:
                self._error(msg["id"], INTERNAL_ERROR, f"internal error: {type(e).__name__}")

    def _dispatch(self, msg: dict, is_request: bool) -> None:
        method = msg["method"]
        rid = msg["id"] if is_request else None
        if not isinstance(method, str):
            self._error(rid, INVALID_REQUEST, "invalid request")
            return
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            if is_request:
                self._error(rid, INVALID_PARAMS, "params must be an object")
            return
        if not is_request:
            if method == "notifications/cancelled":
                self._cancel(params)
            return
        if method == "initialize":
            v = params.get("protocolVersion")
            self._reply(
                rid,
                {
                    "protocolVersion": v if v in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[-1],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "cora", "version": __version__},
                },
            )
        elif method == "ping":
            self._reply(rid, {})
        elif method == "tools/list":
            self._reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            self._tools_call(rid, params)
        else:
            self._error(rid, METHOD_NOT_FOUND, f"method not found: {method}")

    def _tools_call(self, rid: str | int, params: dict) -> None:
        name = params.get("name")
        if name not in TOOL_NAMES:
            self._error(rid, INVALID_PARAMS, f"unknown tool: {name}")
            return
        try:
            args = validate_args(name, params.get("arguments"))
        except InvalidParams as e:
            self._error(rid, INVALID_PARAMS, str(e))
            return
        meta = params.get("_meta")
        token = meta.get("progressToken") if isinstance(meta, dict) else None
        if not _valid_id(token):
            token = None
        if name == "list_sessions":
            doc = list_sessions_doc(self.workdir, args["limit"], self.settings.max_output_chars)
            self._reply(rid, tool_result(doc))
            return
        max_depth = self.settings.max_depth
        if self.depth is None:
            message = (
                f"recursion guard: {DEPTH_ENV}={self.depth_raw!r} is not a non-negative "
                f"integer (limit [mcp] max_depth={max_depth}); refusing to run"
            )
            self._reply(rid, tool_result(_reject_doc(message, "depth_exceeded")))
            return
        if self.depth >= max_depth:
            message = (
                f"recursion guard: {DEPTH_ENV}={self.depth} reaches [mcp] max_depth={max_depth}; "
                "run_task and resume_session are refused inside a served run"
            )
            self._reply(rid, tool_result(_reject_doc(message, "depth_exceeded")))
            return
        run = _Run(rid, token)
        with self._state_lock:
            busy = self._run is not None
            if not busy:
                self._run = run
        if busy:
            self._reply(rid, tool_result(_reject_doc(BUSY_MSG, "busy")))
            return
        thread = threading.Thread(
            target=self._worker, args=(run, name, args), name="cora-mcp-run", daemon=True
        )
        with self._state_lock:
            run.thread = thread
        thread.start()

    def _worker(self, run: _Run, tool: str, args: dict) -> None:
        try:
            doc = self._execute(run, tool, args)
        except Exception as e:
            doc = fit_result(
                error_outcome(f"{type(e).__name__}: {e}", 1), self.settings.max_output_chars
            )
        with self._state_lock:
            run.done = True
            cancelled = run.cancelled
            self._run = None
        if not cancelled:
            self._reply(run.req_id, tool_result(doc))

    def _execute(self, run: _Run, tool: str, args: dict) -> dict:
        start = time.monotonic()
        cap = self.settings.max_output_chars
        warnings = list(self.warnings)
        limits = clamp_limits(args, self.settings)
        cfg = dataclasses.replace(
            self.cfg,
            agent=dataclasses.replace(
                self.cfg.agent,
                approval=self.settings.approval,
                max_cost_usd=limits.cost_usd,
                max_iterations=limits.iterations,
                max_wall_s=limits.wall_s,
                max_tool_calls=limits.tool_calls,
            ),
        )
        manager = McpManager(cfg.mcp, self.workdir)
        try:
            policy = ApprovalPolicy(cfg.agent.approval, review=None)
            governor = BudgetGovernor(
                BudgetLimits.from_agent(cfg.agent),
                warn_fraction=cfg.agent.budget_warn_fraction,
                clock=_clock,
                project_cost=True,
            )

            def handler(ev: dict) -> None:
                if ev["type"] == "budget_warning":
                    pct = round(100 * ev["used"] / ev["limit"])
                    msg = (
                        f"warning: budget {ev['cap']} reached {pct}% of its limit "
                        f"({ev['used']} of {ev['limit']})"
                    )
                    warnings.append(msg)
                    print(msg, file=sys.stderr, flush=True)
                self._progress(run, governor, ev)

            agent = Agent(
                cfg,
                self.workdir,
                policy,
                on_event=handler,
                project_context=load_project_context(self.workdir).render(),
                mcp=manager,
                governor=governor,
            )
            force_delegate_visible(agent)
            warnings += agent.policy_warnings
            with self._state_lock:
                run.agent = agent
                stop = run.cancelled
            if stop:
                agent.request_stop()
            try:
                if tool == "run_task":
                    coro = agent.run(args["task"])
                else:
                    sid = args["session_id"]
                    try:
                        session = agent.sessions.load(sid)
                    except CoraError:
                        doc = error_outcome(
                            f"unknown session id: {sid} (use list_sessions)",
                            1,
                            warnings=warnings,
                        )
                        doc["budget"] = governor.to_dict()
                        return fit_result(doc, cap)
                    if args.get("task"):
                        coro = agent.run(args["task"], session=session)
                    else:
                        coro = agent.resume(sid)
                r = asyncio.run(coro)
            except CoraError as e:
                cost, models = session_totals(agent.current)
                doc = error_outcome(
                    describe_provider_error(e),
                    1,
                    session_id=agent.current.id if agent.current else None,
                    warnings=warnings,
                    wall_s=time.monotonic() - start,
                    cost_usd=cost,
                    models=models,
                )
                doc["budget"] = governor.to_dict()
                return fit_result(doc, cap)
            except Exception as e:
                cost, models = session_totals(agent.current)
                doc = error_outcome(
                    f"{type(e).__name__}: {e}",
                    1,
                    session_id=agent.current.id if agent.current else None,
                    warnings=warnings,
                    wall_s=time.monotonic() - start,
                    cost_usd=cost,
                    models=models,
                )
                doc["budget"] = governor.to_dict()
                return fit_result(doc, cap)
            doc = outcome_dict(
                r,
                governor,
                wall_s=time.monotonic() - start,
                warnings=warnings,
                denials=policy.denied,
            )
            return fit_result(doc, cap)
        finally:
            manager.close()

    def _progress(self, run: _Run, governor: BudgetGovernor, ev: dict) -> None:
        if run.token is None or ev["type"] not in PROGRESS_EVENTS:
            return
        now = _progress_clock()
        with self._state_lock:
            if run.done or run.cancelled:
                return
            if run.last_progress is not None and now - run.last_progress < PROGRESS_INTERVAL_S:
                return
            run.last_progress = now
            run.progress_n += 1
            n = run.progress_n
        usage = governor.usage()
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": run.token,
                    "progress": n,
                    "message": f"iteration {usage.iterations}, cost ${usage.cost_usd:.4f}",
                },
            }
        )

    def _cancel(self, params: dict) -> None:
        rid = params.get("requestId")
        with self._state_lock:
            run = self._run
            if (
                run is None
                or run.done
                or type(rid) is not type(run.req_id)
                or rid != run.req_id
            ):
                return
            run.cancelled = True
            agent = run.agent
        if agent is not None:
            agent.request_stop()
        print(f"cora mcp serve: cancel requested for {rid}", file=sys.stderr)

    def shutdown(self) -> None:
        agent = None
        thread = None
        with self._state_lock:
            run = self._run
            if run is not None and not run.done:
                run.cancelled = True
                agent = run.agent
                thread = run.thread
        if agent is not None:
            agent.request_stop()
        if thread is not None:
            thread.join()
        with self._write_lock:
            try:
                self.out.flush()
            except OSError:
                pass


def serve(
    config: Path | None,
    workdir: Path,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> int:
    workdir = Path(workdir).resolve()
    try:
        _, cfg = load_resolved(find_config(config), workdir)
    except CoraError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    warnings = [*cfg.mcp.warnings, *unpriced_warnings(cfg)]
    for w in warnings:
        print(w, file=sys.stderr)
    raw = os.environ.get(DEPTH_ENV)
    depth = parse_depth(raw)
    previous = raw
    if depth is not None:
        os.environ[DEPTH_ENV] = str(depth + 1)
    inp = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout.buffer
    saved = sys.stdout
    sys.stdout = sys.stderr
    settings = cfg.mcp.serve
    server = McpServer(
        cfg,
        workdir,
        out,
        depth=depth,
        depth_raw=raw if raw is not None else "",
        warnings=warnings,
    )
    try:
        shown = raw if raw else "0"
        print(
            f"cora mcp serve: ready (protocol {PROTOCOL_VERSION}, depth {shown}, "
            f"max_depth {settings.max_depth}, approval {settings.approval})",
            file=sys.stderr,
        )
        if settings.approval == "policy":
            print(POLICY_MODE_NOTICE, file=sys.stderr)
        while True:
            line = inp.readline(MAX_MESSAGE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_MESSAGE_BYTES and not line.endswith(b"\n"):
                while True:
                    chunk = inp.readline(MAX_MESSAGE_BYTES + 1)
                    if not chunk or chunk.endswith(b"\n"):
                        break
                server._error(None, INVALID_REQUEST, "message too large")
            else:
                server.handle_line(line)
    finally:
        server.shutdown()
        sys.stdout = saved
        if previous is None:
            os.environ.pop(DEPTH_ENV, None)
        else:
            os.environ[DEPTH_ENV] = previous
    return 0
