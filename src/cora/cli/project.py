from __future__ import annotations

import asyncio
import dataclasses
import json
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from cora.cli.common import (
    apply_agent_overrides,
    force_delegate_visible,
    load_resolved,
    run_interruptible,
    unpriced_warnings,
)
from cora.cli.headless import HeadlessOptions, HeadlessUsageError, headless_approval, run_graceful
from cora.core.agent import Agent
from cora.core.budget import BudgetGovernor, BudgetLimits
from cora.core.config import find_config
from cora.core.errors import (
    ConfigError,
    CoraError,
    MissingAPIKeyError,
    ProviderAccountError,
    describe_provider_error,
)
from cora.core.metering import CostMeter
from cora.core.milestones import (
    Checkpoint,
    CheckpointStore,
    PlanError,
    ProjectGovernor,
    ProjectRunner,
    atomic_write_text,
    checkpoint_totals,
    load_plan,
    plan_to_toml,
    project_error_outcome,
    project_outcome,
)
from cora.core.observability import EventLog
from cora.core.outcome import metered_totals
from cora.core.planner import (
    UNGATED_WARNING,
    PlanBudgetExceeded,
    generate_plan,
    plan_error_outcome,
    plan_outcome,
)
from cora.core.policy import POLICY_MODE_NOTICE, planning_policy
from cora.core.project import load_project_context
from cora.core.tools import ApprovalPolicy, ApprovalRequest
from cora.core.tools.mcp import McpManager

_clock = time.monotonic


def _planner_log(workdir: Path) -> tuple[Callable[[str, dict], None], list[tuple[str, dict]]]:
    buffer: list[tuple[str, dict]] = []
    log: EventLog | None = None

    def emit(event_type: str, data: dict) -> None:
        nonlocal log
        buffer.append((event_type, data))
        if log is None:
            log = EventLog(Path(workdir) / ".cora" / "planner" / "events.jsonl")
        log.emit(event_type, **data)

    return emit, buffer


@dataclass(frozen=True)
class ProjectOptions:
    workdir: Path
    config: Path | None
    plan: Path | None = None
    run_id: str | None = None
    headless: bool = False
    json: bool = False
    quiet: bool = False
    verbose: bool = False
    approval: str | None = None
    max_iterations: int | None = None
    max_cost: float | None = None
    max_wall_s: float | None = None
    max_tool_calls: int | None = None
    goal: str | None = None
    output: Path | None = None


def run_project(
    opts: ProjectOptions,
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
            if ev["type"] == "milestone_start":
                typer.echo(f"[milestone] {ev['id']} started", err=True)
            if ev["type"] == "milestone_end":
                typer.echo(
                    f"[milestone] {ev['id']} {ev['status']} ({ev['stop_reason']})", err=True
                )
            if ev["type"] == "gate":
                typer.echo(
                    f"[gate] {ev['id']} attempt {ev['attempt']}: "
                    + ("passed" if ev["passed"] else f"failed ({ev['condition']})"),
                    err=True,
                )
            progress(ev)

    running = False
    manager: McpManager | None = None
    policy: ApprovalPolicy | None = None
    governor: ProjectGovernor | None = None
    runner: ProjectRunner | None = None
    cp: Checkpoint | None = None
    stop: str | None = None
    legacy: int | None = None
    sig: int | None = None
    doc: dict | None = None
    plan_meter: CostMeter | None = None

    def spent() -> tuple[float, list[str]]:
        if running and cp is not None:
            return checkpoint_totals(cp)
        if plan_meter is not None and plan_meter.records:
            return metered_totals(plan_meter)
        return 0.0, []

    try:
        store = CheckpointStore(Path(opts.workdir) / ".cora" / "projects")
        if opts.run_id is None and opts.plan is not None and opts.goal is not None:
            raise HeadlessUsageError("give either a plan file or --goal, not both")
        if opts.output is not None and opts.goal is None:
            raise HeadlessUsageError("-o/--output requires --goal")
        if opts.run_id is not None:
            cp = store.load(opts.run_id)
            plan = cp.plan
        elif opts.goal is not None:
            if not opts.goal.strip():
                raise HeadlessUsageError("--goal must not be empty")
            plan = None
        else:
            if opts.plan is None:
                raise HeadlessUsageError("no plan file given (pass PLAN.toml or --goal GOAL)")
            plan = load_plan(opts.plan)
        _, cfg = load_resolved(find_config(opts.config), opts.workdir)
        for w in unpriced_warnings(cfg):
            warn(w)
        approval = headless_approval(
            HeadlessOptions(
                task=None,
                workdir=opts.workdir,
                config=opts.config,
                headless=opts.headless,
                approval=opts.approval,
            ),
            warn,
        )
        cfg = apply_agent_overrides(
            cfg,
            approval,
            opts.max_iterations,
            opts.max_cost,
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
        governor = ProjectGovernor(
            BudgetLimits.from_agent(cfg.agent),
            base=cp.budget_used if cp is not None else None,
            warn_fraction=cfg.agent.budget_warn_fraction,
            clock=_clock,
            project_cost=True,
        )
        planning = None
        planner_events: list[tuple[str, dict]] = []
        if plan is None:
            meter = plan_meter = CostMeter()
            plan_pol = planning_policy(cfg.policy, Path(opts.workdir), cfg.agent.approval)
            plan_emit, planner_events = _planner_log(Path(opts.workdir))
            plan, planning = asyncio.run(generate_plan(
                opts.goal, cfg, governor, meter=meter,
                max_milestones=cfg.project.max_milestones,
                policy=plan_pol,
                on_event=plan_emit,
                workspace=Path(opts.workdir),
            ))
            governor.commit()
            if opts.output is not None:
                try:
                    atomic_write_text(opts.output, plan_to_toml(plan))
                except OSError as e:
                    raise PlanError(f"cannot write plan file {opts.output}: {e}") from e
            note(f"planned {len(plan.milestones)} milestones (cost ${planning['cost_usd']:.4f})")
            pp = planning.get("policy")
            if pp:
                if pp["dropped"]:
                    note(
                        f"plan: {pp['dropped']} check(s) denied by the policy were dropped "
                        f"({pp['repaired']} repaired)"
                    )
                for mid in pp["ungated"]:
                    warn(UNGATED_WARNING.format(id=mid))
        context = load_project_context(opts.workdir).render()

        def make_agent() -> Agent:
            a = Agent(
                cfg,
                opts.workdir,
                policy,
                on_event=handler,
                project_context=context,
                mcp=manager,
                governor=governor,
            )
            force_delegate_visible(a)
            return a

        first = [make_agent()]
        def factory() -> Agent:
            return first.pop() if first else make_agent()

        for w in first[0].policy_warnings:
            warn(w)
        if cfg.agent.approval == "policy":
            note(POLICY_MODE_NOTICE)
        if cp is None:
            cp = store.create(plan, planning=planning)
            if planning is not None:
                atomic_write_text(store.dir_for(cp.run_id) / "plan.toml", plan_to_toml(plan))
        note(f"project run id: {cp.run_id}")
        runner = ProjectRunner(
            cp,
            store,
            governor,
            factory,
            denials=lambda: policy.denied,
            on_event=handler,
            gate_retries=cfg.project.gate_retries,
            condition_timeout_s=cfg.project.condition_timeout_s,
            condition_output_chars=cfg.project.condition_output_chars,
        )
        for event_type, data in planner_events:
            runner.log.emit(event_type, **data)
        if planning is not None and planning.get("policy") is not None:
            runner.log.emit("plan_policy", **planning["policy"])
        running = True
        if opts.headless:
            stop, sig = run_graceful(runner, runner.execute())
        else:
            try:
                stop = run_interruptible(runner.execute())
            except KeyboardInterrupt:
                sig = signal.SIGINT
                stop = None
        if stop is None:
            stop = "interrupted"
    except CoraError as e:
        msg = describe_provider_error(e)
        errors.append(msg)
        typer.echo(f"error: {msg}", err=True)
        stop_reason = "error"
        if isinstance(e, PlanBudgetExceeded):
            code, legacy, stop_reason = 4, 1, "budget_exceeded"
        else:
            code = (
                2
                if not running
                or isinstance(e, (ConfigError, MissingAPIKeyError, ProviderAccountError))
                else 1
            )
            legacy = 2
        cost, models = spent()
        doc = project_error_outcome(
            msg,
            code,
            checkpoint=cp,
            session_id=runner.last_session_id if runner is not None else None,
            warnings=warnings,
            wall_s=time.monotonic() - start,
            stop_reason=stop_reason,
            cost_usd=cost,
            models=models,
        )
        if isinstance(e, PlanBudgetExceeded) and governor is not None:
            doc["budget"] = governor.to_dict()
    except Exception as e:
        if not running:
            raise
        msg = f"{type(e).__name__}: {e}"
        errors.append(msg)
        typer.echo(f"error: {msg}", err=True)
        legacy = 1
        cost, models = spent()
        doc = project_error_outcome(
            msg,
            1,
            checkpoint=cp,
            session_id=runner.last_session_id if runner is not None else None,
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
        doc = project_outcome(
            cp,
            governor,
            stop_reason=stop,
            wall_s=time.monotonic() - start,
            warnings=warnings,
            errors=errors,
            signal=sig,
            session_id=runner.last_session_id if runner is not None else None,
        )

    if opts.json:
        real_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
        real_out.flush()
    else:
        if doc["final_answer"] is not None:
            typer.echo(doc["final_answer"])
        if not opts.quiet and doc["run_id"]:
            for m in doc["milestones"]:
                typer.echo(f"  {m['id']}: {m['status']}", err=True)
                if m.get("gate") and m["gate"]["failed_condition"] and m["status"] == "failed":
                    typer.echo(
                        f"    gate: {m['gate']['failed_condition']} failed after "
                        f"{m['gate']['attempts']} attempt(s)",
                        err=True,
                    )
            if doc.get("ungated_milestones"):
                typer.echo(
                    f"ungated milestones: {', '.join(doc['ungated_milestones'])}", err=True
                )
            typer.echo(f"stop_reason: {doc['stop_reason']}", err=True)
            typer.echo(f"run: {doc['run_id']}", err=True)
        if running and not doc["ok"]:
            typer.echo(f"resume with: cora project resume {doc['run_id']}", err=True)

    if machine:
        return int(doc["exit_code"])
    if legacy is not None:
        return legacy
    if doc["stop_reason"] == "interrupted":
        return 130
    return 0 if doc["ok"] else 1


@dataclass(frozen=True)
class PlanOptions:
    goal: str
    output: Path | None
    workdir: Path
    config: Path | None
    json: bool = False
    quiet: bool = False
    max_cost: float | None = None
    approval: str | None = None


def run_plan(opts: PlanOptions) -> int:
    start = time.monotonic()
    warnings: list[str] = []
    real_out = sys.stdout
    if opts.json:
        sys.stdout = sys.stderr
    meter = CostMeter()
    governor: BudgetGovernor | None = None
    doc: dict | None = None
    try:
        if not opts.goal.strip():
            raise HeadlessUsageError("GOAL must not be empty")
        if opts.output is None:
            raise HeadlessUsageError("missing -o/--output PLAN.toml")
        _, cfg = load_resolved(find_config(opts.config), opts.workdir)
        for w in unpriced_warnings(cfg):
            typer.echo(w, err=True)
            warnings.append(w)
        cfg = apply_agent_overrides(cfg, opts.approval, None, opts.max_cost)
        governor = BudgetGovernor(
            BudgetLimits.from_agent(cfg.agent),
            warn_fraction=cfg.agent.budget_warn_fraction,
            clock=_clock,
            project_cost=True,
        )
        pol = planning_policy(cfg.policy, Path(opts.workdir), cfg.agent.approval)
        plan_emit, _ = _planner_log(Path(opts.workdir))
        plan, info = asyncio.run(generate_plan(
            opts.goal, cfg, governor, meter=meter,
            max_milestones=cfg.project.max_milestones,
            policy=pol,
            on_event=plan_emit,
            workspace=Path(opts.workdir),
        ))
        pp = info["policy"]
        if pp:
            if pp["dropped"] and not opts.quiet:
                typer.echo(
                    f"plan: {pp['dropped']} check(s) denied by the policy were dropped "
                    f"({pp['repaired']} repaired)",
                    err=True,
                )
            for mid in pp["ungated"]:
                w = UNGATED_WARNING.format(id=mid)
                typer.echo(w, err=True)
                warnings.append(w)
        try:
            atomic_write_text(opts.output, plan_to_toml(plan))
        except OSError as e:
            raise PlanError(f"cannot write plan file {opts.output}: {e}") from e
        doc = plan_outcome(
            opts.output, plan, meter, governor,
            wall_s=time.monotonic() - start, warnings=warnings,
            plan_policy=info["policy"],
        )
    except PlanBudgetExceeded as e:
        msg = str(e)
        typer.echo(f"error: {msg}", err=True)
        doc = plan_error_outcome(
            msg, 4, goal=opts.goal, meter=meter, governor=governor,
            wall_s=time.monotonic() - start, warnings=warnings, stop_reason="budget_exceeded",
        )
    except CoraError as e:
        msg = describe_provider_error(e)
        typer.echo(f"error: {msg}", err=True)
        doc = plan_error_outcome(
            msg, 2, goal=opts.goal, meter=meter, governor=governor,
            wall_s=time.monotonic() - start, warnings=warnings,
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        typer.echo(f"error: {msg}", err=True)
        doc = plan_error_outcome(
            msg, 2, goal=opts.goal, meter=meter, governor=governor,
            wall_s=time.monotonic() - start, warnings=warnings,
        )
    finally:
        sys.stdout = real_out

    if opts.json:
        real_out.write(json.dumps(doc, ensure_ascii=False) + "\n")
        real_out.flush()
    elif doc["ok"]:
        typer.echo(doc["path"])
        if not opts.quiet:
            typer.echo(
                f"plan: {doc['milestone_count']} milestones, cost ${doc['cost_usd']:.4f}",
                err=True,
            )
    return int(doc["exit_code"])
