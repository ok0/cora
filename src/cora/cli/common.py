from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from cora.core.agent import Agent
from cora.core.config import (
    APPROVAL_MODES,
    CoraConfig,
    load_config,
    load_user_overrides,
    resolve_config,
    unpriced_models,
    user_models_path,
)
from cora.core.errors import ConfigError

MCP_NONE = (
    "No MCP servers configured. Add a [mcp.servers.<name>] table to cora.toml "
    "(command, optional args, env, enabled, timeout_s) and restart CORA; see USAGE.md."
)


def mcp_tool_list(names: list[str], limit: int = 8) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f" (+{len(names) - limit} more)" if len(names) > limit else "")


def parse_price(value: str) -> tuple[float, float]:
    parts = value.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    raise ConfigError(f"price must be IN,OUT (USD per 1M tokens), got '{value}'")


def apply_agent_overrides(
    cfg: CoraConfig,
    approval: str | None,
    max_iterations: int | None,
    max_cost: float | None,
    delegate: bool = False,
    *,
    max_wall_s: float | None = None,
    max_tool_calls: int | None = None,
) -> CoraConfig:
    agent = cfg.agent
    if approval is not None and approval not in APPROVAL_MODES:
        raise ConfigError(
            f"invalid --approval '{approval}'; expected one of {list(APPROVAL_MODES)}"
        )
    if max_iterations is not None and max_iterations < 0:
        raise ConfigError("invalid --max-iterations: must be an integer >= 0")
    if max_cost is not None and max_cost < 0:
        raise ConfigError("invalid --max-cost: must be a number >= 0")
    if max_wall_s is not None and max_wall_s < 0:
        raise ConfigError("invalid --max-wall-s: must be a number >= 0 (0 = unlimited)")
    if max_tool_calls is not None and max_tool_calls < 0:
        raise ConfigError("invalid --max-tool-calls: must be an integer >= 0 (0 = unlimited)")
    if approval is not None:
        agent = dataclasses.replace(agent, approval=approval)
    if max_iterations is not None:
        agent = dataclasses.replace(agent, max_iterations=max_iterations)
    if max_cost is not None:
        agent = dataclasses.replace(agent, max_cost_usd=max_cost)
    if max_wall_s is not None:
        agent = dataclasses.replace(agent, max_wall_s=max_wall_s)
    if max_tool_calls is not None:
        agent = dataclasses.replace(agent, max_tool_calls=max_tool_calls)
    out = dataclasses.replace(cfg, agent=agent)
    if delegate:
        out = dataclasses.replace(out, delegation=dataclasses.replace(out.delegation, enabled=True))
    return out


def force_delegate_visible(agent: Agent) -> None:
    """Applies M18b R8: a run started with delegation enabled always shows the delegate group."""
    if agent.config.delegation.enabled:
        agent.ctx.forced_groups = agent.ctx.forced_groups | frozenset({"delegate"})


def load_resolved(config_path: Path, workdir: Path) -> tuple[CoraConfig, CoraConfig]:
    base = load_config(config_path)
    return base, resolve_config(base, load_user_overrides(user_models_path(workdir)), [])


def unpriced_warnings(cfg: CoraConfig) -> list[str]:
    return [
        f"warning: model '{m.id}' (tier {m.tier}) has no known price; cost will be "
        "reported as 'unknown' and counted as $0 toward --max-cost. Set it with "
        f"/model {m.tier} {m.id} IN,OUT."
        for m in unpriced_models(cfg)
    ]


def fmt_price(v: float | None) -> str:
    return "unknown" if v is None else f"{v:g}"


def normalize_answer(ans: str) -> str:
    value = ans.strip().lower()
    if value in ("y", "yes"):
        return "yes"
    if value in ("a", "always"):
        return "always"
    return "no"


def tool_line(event: dict) -> str:
    head = f"● {event['tool']}" + (f" {event.get('target')}" if event.get("target") else "")
    if event["ok"]:
        return f"{head} ({event.get('output_lines', 0)} lines)"
    first = (event.get("output_head") or "").split("\n", 1)[0][:120]
    return f"{head} (failed: {first})"


class CancelScope:
    """Lets another thread (the TUI) cancel the task run_interruptible is running."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self.cancelled = False

    def bind(self, loop: asyncio.AbstractEventLoop, task: asyncio.Task) -> None:
        with self._lock:
            self._loop, self._task, self.cancelled = loop, task, False

    def unbind(self) -> None:
        with self._lock:
            self._loop = None
            self._task = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._task is not None and not self._task.done()

    def cancel(self) -> bool:
        with self._lock:
            if self._loop is None or self._task is None or self._task.done():
                return False
            try:
                self._loop.call_soon_threadsafe(self._task.cancel)
            except RuntimeError:
                return False
            self.cancelled = True
            return True


def run_interruptible[T](coro: Coroutine[Any, Any, T], scope: CancelScope | None = None) -> T:
    loop = asyncio.new_event_loop()
    task = loop.create_task(coro)
    if scope is not None:
        scope.bind(loop, task)
    try:
        try:
            return loop.run_until_complete(task)
        except asyncio.CancelledError:
            if scope is not None and scope.cancelled:
                raise KeyboardInterrupt from None
            raise
    except KeyboardInterrupt:
        if not task.done():
            task.cancel()
            with contextlib.suppress(BaseException):
                loop.run_until_complete(task)
        if task.done() and not task.cancelled():
            with contextlib.suppress(BaseException):
                task.exception()
        raise
    finally:
        if scope is not None:
            scope.unbind()
        with contextlib.suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
