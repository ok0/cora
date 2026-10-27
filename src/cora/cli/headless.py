from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import signal
import sys
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import typer

from cora.cli.common import (
    apply_agent_overrides,
    force_delegate_visible,
    load_resolved,
    run_interruptible,
    unpriced_warnings,
)
from cora.core.agent import Agent, RunResult
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.config import find_config
from cora.core.errors import (
    ConfigError,
    CoraError,
    MissingAPIKeyError,
    ProviderAccountError,
    describe_provider_error,
)
from cora.core.metering import format_summary
from cora.core.outcome import (
    error_outcome,
    exit_code,
    interrupted_result,
    outcome_dict,
    session_totals,
)
from cora.core.policy import POLICY_MODE_NOTICE
from cora.core.project import load_project_context
from cora.core.tools import ApprovalPolicy, ApprovalRequest
from cora.core.tools.mcp import McpManager

_clock = time.monotonic
_SIGNALS = (signal.SIGINT, signal.SIGTERM)


class HeadlessUsageError(CoraError):
    pass


@dataclass(frozen=True)
class HeadlessOptions:
    task: str | None
    workdir: Path
    config: Path | None
    task_file: Path | None = None
    headless: bool = False
    json: bool = False
    quiet: bool = False
    verbose: bool = False
    approval: str | None = None
    max_iterations: int | None = None
    max_cost: float | None = None
    max_wall_s: float | None = None
    max_tool_calls: int | None = None
    check: str | None = None
    delegate: bool = False
    resume_id: str | None = None


def read_task(task: str | None, task_file: Path | None) -> str | None:
    n = (task is not None) + (task_file is not None)
    if n > 1:
        raise HeadlessUsageError(
            "give exactly one task source: TASK, --task-file PATH, or - for stdin"
        )
    if n == 0:
        return None
    if task == "-":
        text = sys.stdin.read()
    elif task_file is not None:
        try:
            text = task_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise HeadlessUsageError(f"cannot read --task-file {task_file}: {e}") from e
    else:
        text = task or ""
    if not text.strip():
        raise HeadlessUsageError("the task is empty")
    return text.strip()


def headless_approval(opts: HeadlessOptions, warn: Callable[[str], None]) -> str | None:
    if not opts.headless:
        return opts.approval
    mode = opts.approval or "policy"
    if mode == "ask":
        raise HeadlessUsageError(
            "--approval ask is not allowed with --headless (nobody can answer prompts); "
            "use policy (default), deny or auto"
        )
    if mode == "auto":
        warn("warning: --approval auto runs every tool call without review in an unattended run")
    return mode


class Stoppable(Protocol):
    def request_stop(self) -> None: ...


def run_graceful[T](
    target: Stoppable, coro: Coroutine[Any, Any, T]
) -> tuple[T | None, int | None]:
    loop = asyncio.new_event_loop()
    task = loop.create_task(coro)
    got: list[int] = []
    previous = {s: signal.getsignal(s) for s in _SIGNALS}

    def on_signal(signum: int) -> None:
        got.append(signum)
        if len(got) == 1:
            target.request_stop()
        else:
            task.cancel()

    try:
        for s in _SIGNALS:
            try:
                loop.add_signal_handler(s, on_signal, s)
            except NotImplementedError:
                signal.signal(
                    s, lambda n, _f: loop.call_soon_threadsafe(on_signal, n)
                )
        try:
            result = loop.run_until_complete(task)
        except asyncio.CancelledError:
            return None, got[0] if got else signal.SIGINT
        return result, got[0] if got else None
    finally:
        for s in _SIGNALS:
            with contextlib.suppress(Exception):
                loop.remove_signal_handler(s)
            if previous[s] is not None:
                with contextlib.suppress(Exception):
                    signal.signal(s, previous[s])
        with contextlib.suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def run_headless(
    opts: HeadlessOptions,
    *,
    progress: Callable[[dict], None],
    review: Callable[[ApprovalRequest], str],
) -> int:
    start = time.monotonic()
    warnings: list[str] = []
    errors: list[str] = []
    machine = opts.headless or opts.json
    real_out = sys.stdout
    if opts.json:
        sys.stdout = sys.stderr

    def warn(msg: str) -> None:
        if machine:
            warnings.append(msg)
        typer.echo(msg, err=True)

    def note(msg: str) -> None:
        if not opts.quiet:
            typer.echo(msg, err=True)

    def handler(ev: dict) -> None:
        if ev["type"] == "budget_warning" and machine:
            pct = round(100 * ev["used"] / ev["limit"])
            warn(
                f"warning: budget {ev['cap']} reached {pct}% of its limit "
                f"({ev['used']} of {ev['limit']})"
            )
        if not opts.quiet:
            progress(ev)

    running = False
    manager: McpManager | None = None
    agent: Agent | None = None
    policy: ApprovalPolicy | None = None
    governor: BudgetGovernor | None = None
    legacy: int | None = None
    sig: int | None = None
    r: RunResult | None = None
    doc: dict | None = None
    try:
        if opts.resume_id and not opts.headless:
            raise HeadlessUsageError("--resume needs --headless; use `cora resume ID` otherwise")
        task = read_task(opts.task, opts.task_file)
        if task is None and opts.resume_id is None:
            raise HeadlessUsageError(
                "no task given: pass TASK, --task-file PATH, or - to read stdin"
            )
        _, cfg = load_resolved(find_config(opts.config), opts.workdir)
        for w in unpriced_warnings(cfg):
            warn(w)
        approval = headless_approval(opts, warn)
        cfg = apply_agent_overrides(
            cfg,
            approval,
            opts.max_iterations,
            opts.max_cost,
            delegate=opts.delegate,
            max_wall_s=opts.max_wall_s,
            max_tool_calls=opts.max_tool_calls,
        )
        if opts.headless:
            headless_caps = {}
            if opts.max_wall_s is None:
                headless_caps["max_wall_s"] = cfg.headless.max_wall_s
            if opts.max_tool_calls is None:
                headless_caps["max_tool_calls"] = cfg.headless.max_tool_calls
            cfg = dataclasses.replace(
                cfg, agent=dataclasses.replace(cfg.agent, **headless_caps)
            )
        for w in cfg.mcp.warnings:
            warn(w)
        manager = McpManager(cfg.mcp, Path(opts.workdir).resolve())
        policy = ApprovalPolicy(
            cfg.agent.approval, review=None if opts.headless else review
        )
        governor = BudgetGovernor(
            BudgetLimits.from_agent(cfg.agent),
            warn_fraction=cfg.agent.budget_warn_fraction,
            clock=_clock,
            project_cost=True,
        )
        agent = Agent(
            cfg,
            opts.workdir,
            policy,
            on_event=handler,
            project_context=load_project_context(opts.workdir).render(),
            mcp=manager,
            governor=governor,
        )
        force_delegate_visible(agent)
        for w in agent.policy_warnings:
            warn(w)
        if cfg.agent.approval == "policy":
            note(POLICY_MODE_NOTICE)
        session = agent.sessions.load(opts.resume_id) if opts.resume_id else None
        running = True
        coro = (
            agent.run(task, check_command=opts.check, session=session)
            if task is not None
            else agent.resume(opts.resume_id or "")
        )
        if opts.headless:
            r, sig = run_graceful(agent, coro)
        else:
            try:
                r = run_interruptible(coro)
            except KeyboardInterrupt:
                sig = signal.SIGINT
                r = None
        if r is None and agent.current is not None:
            r = interrupted_result(
                agent.current, agent.sessions.dir_for(agent.current.id) / "events.jsonl"
            )
    except CoraError as e:
        msg = describe_provider_error(e)
        errors.append(msg)
        typer.echo(f"error: {msg}", err=True)
        code = (
            2
            if not running or isinstance(e, (ConfigError, MissingAPIKeyError, ProviderAccountError))
            else 1
        )
        legacy = 2
        cost, models = session_totals(agent.current if running and agent is not None else None)
        doc = error_outcome(
            msg,
            code,
            session_id=agent.current.id if agent is not None and agent.current else None,
            warnings=warnings,
            wall_s=time.monotonic() - start,
            cost_usd=cost,
            models=models,
        )
    except Exception as e:
        if not running:
            raise
        msg = f"{type(e).__name__}: {e}"
        errors.append(msg)
        typer.echo(f"error: {msg}", err=True)
        legacy = 1
        cost, models = session_totals(agent.current if running and agent is not None else None)
        doc = error_outcome(
            msg,
            1,
            session_id=agent.current.id if agent is not None and agent.current else None,
            warnings=warnings,
            wall_s=time.monotonic() - start,
            cost_usd=cost,
            models=models,
        )
    finally:
        if manager is not None:
            manager.close()
        sys.stdout = real_out

    if doc is None:
        if r is None:
            doc = error_outcome(
                "interrupted before the session started",
                exit_code("interrupted", signal=sig),
                warnings=warnings,
                wall_s=time.monotonic() - start,
                stop_reason="interrupted",
            )
        else:
            doc = outcome_dict(
                r,
                governor,
                wall_s=time.monotonic() - start,
                warnings=warnings,
                errors=errors,
                denials=policy.denied if policy is not None else 0,
                signal=sig,
            )

    if opts.json:
        real_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
        real_out.flush()
    elif r is not None:
        if r.answer is not None:
            typer.echo(r.answer)
        raw = str(r.stop_reason)
        if not opts.quiet:
            typer.echo(f"stop_reason: {raw}", err=True)
            typer.echo(format_summary(r.summary), err=True)
            typer.echo(f"session: {r.session.id} (log: {r.log_path})", err=True)
        tripped = doc["budget"]["tripped"] if doc["budget"] else None
        if raw == "budget_exceeded" or tripped:
            typer.echo(
                f"budget exceeded: {tripped} cap reached; resume with: cora resume "
                f"{r.session.id}",
                err=True,
            )
    if not opts.json and doc["stop_reason"] == "interrupted":
        sid = doc["session_id"] or "<id>"
        typer.echo(f"interrupted; resume with: cora resume {sid}", err=True)

    if machine:
        return int(doc["exit_code"])
    if legacy is not None:
        return legacy
    if doc["stop_reason"] == "interrupted":
        return 130
    return 0 if doc["ok"] else 1
