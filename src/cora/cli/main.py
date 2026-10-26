from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
import math
import os
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from cora import __version__
from cora.cli.common import (
    MCP_NONE,
    apply_agent_overrides,
    force_delegate_visible,
    load_resolved,
    normalize_answer,
    run_interruptible,
    tool_line,
    unpriced_warnings,
)
from cora.cli.headless import HeadlessOptions, run_headless
from cora.cli.io import PlainIO, TerminalIO
from cora.cli.mcp_serve import serve as mcp_serve
from cora.cli.mode import choose_ui, interactive_terminal
from cora.cli.project import PlanOptions, ProjectOptions, run_plan, run_project
from cora.cli.repl import COMMANDS, Repl, ReplOptions
from cora.core.agent import Agent, RunResult
from cora.core.config import check_decider_model, find_config, load_config, secret_env_names
from cora.core.errors import ConfigError, CoraError, describe_provider_error
from cora.core.metering import format_summary
from cora.core.policy import POLICY_MODE_NOTICE
from cora.core.project import load_project_context
from cora.core.sale import load_tier_table
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy, ApprovalRequest
from cora.core.tools.mcp import McpManager

if TYPE_CHECKING:
    from cora.bench.e2e import E2ETask
    from cora.bench.live_tasks import LiveTask
    from cora.bench.plan import BudgetPlan, UnitKey
    from cora.bench.report import LiveReport, LiveTaskResult

app = typer.Typer(
    add_completion=False,
    help=(
        "CORA - Cost-Oriented Routing Agent. Run `cora` with no arguments for the "
        "interactive session (/help inside)."
    ),
)

WorkdirOpt = Annotated[Path, typer.Option("--workdir", "-w")]
ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c")]
ApprovalOpt = Annotated[str | None, typer.Option("--approval")]
MaxIterationsOpt = Annotated[int | None, typer.Option("--max-iterations")]
MaxCostOpt = Annotated[float | None, typer.Option("--max-cost")]
RepeatsOpt = Annotated[
    int | None,
    typer.Option("--repeats", min=1, help="Run every cell N times (integer >= 1, default 1)"),
]
SeedOpt = Annotated[
    int | None,
    typer.Option(
        "--seed",
        help="Base seed (default 0); run seed = base + repeat index (recorded, not sent to "
        "providers)",
    ),
]
SuiteOpt = Annotated[
    str,
    typer.Option(
        "--suite",
        help="Task suite: default (built-in live tasks) or e2e (end-to-end project tasks, --live)",
    ),
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v")]
PrintOpt = Annotated[
    str | None,
    typer.Option(
        "--print",
        "-p",
        help="Run one task non-interactively; answer on stdout, progress on stderr",
    ),
]
DelegateOpt = Annotated[
    bool,
    typer.Option(
        "--delegate",
        help="Enable sub-agent delegation for this run (default: [delegation].enabled)",
    ),
]
HeadlessOpt = Annotated[
    bool,
    typer.Option("--headless", help=(
        "Unattended run: no TUI, REPL or prompts; approval defaults to policy")),
]
JsonOpt = Annotated[
    bool,
    typer.Option("--json", help="Print exactly one JSON result document on stdout"),
]
QuietOpt = Annotated[
    bool,
    typer.Option("--quiet", "-q", help=(
        "No progress on stderr (errors and warnings still shown)")),
]
TaskFileOpt = Annotated[Path | None, typer.Option("--task-file", help="Read the task from a file")]
MaxWallOpt = Annotated[
    float | None,
    typer.Option("--max-wall-s", help="Wall-clock cap in seconds (0 = unlimited)"),
]
MaxToolCallsOpt = Annotated[
    int | None,
    typer.Option("--max-tool-calls", help="Tool-call cap incl. sub-agents (0 = unlimited)"),
]
ResumeIdOpt = Annotated[
    str | None,
    typer.Option("--resume", help="With --headless: continue a stored session (TASK optional)"),
]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cora {__version__}")
        raise typer.Exit()


TuiOpt = Annotated[bool | None, typer.Option("--tui/--no-tui", help=(
    "Full-screen TUI on an interactive terminal (default: CORA_TUI, then [ui] tui = true); "
    "pipes, cora -p/run, non-interactive cora resume and TERM=dumb never use it"))]
VersionOpt = Annotated[bool, typer.Option("--version", callback=_version_callback,
                                          is_eager=True, help="Show the CORA version and exit")]


def _stderr_events(verbose: bool) -> Callable[[dict], None]:
    def handle(event: dict) -> None:
        if event["type"] == "route":
            typer.echo(
                f"[route] grade={event.get('grade', 'unknown')} tier={event['tier']} "
                f"model={event['model']} score={event['score']} reasons={event['reasons']}",
                err=True,
            )
        if event["type"] == "tool_call":
            typer.echo(tool_line(event), err=True)
        if event["type"] == "stop":
            typer.echo(f"[stop] {event['reason']}", err=True)
        if event["type"] == "policy_decision" and event.get("resolved") == "deny":
            typer.echo(f"[policy] {event['decision']} {event['tool']} ({event['rule']})",
                       err=True)
        if verbose:
            typer.echo(json.dumps(event, ensure_ascii=False), err=True)

    return handle


def _stderr_review(req: ApprovalRequest) -> str:
    typer.echo(f"approval required: {req.tool}", err=True)
    if req.detail:
        typer.echo(req.detail, err=True)
    try:
        ans = typer.prompt("Allow? [y]es / [n]o / [a]lways this session", default="n", err=True)
    except (typer.Abort, EOFError):
        return "no"
    return normalize_answer(ans)


def _policy_notices(agent: Agent, approval: str) -> None:
    for w in agent.policy_warnings:
        typer.echo(w, err=True)
    if approval == "policy":
        typer.echo(POLICY_MODE_NOTICE, err=True)


def _wants_headless(
    task: str | None,
    headless: bool,
    json_: bool,
    quiet: bool,
    task_file: Path | None,
    resume_id: str | None,
) -> bool:
    return (
        headless
        or json_
        or quiet
        or task_file is not None
        or resume_id is not None
        or task == "-"
        or task is None
    )


def _emit_result(r: RunResult) -> None:
    if r.answer is not None:
        typer.echo(r.answer)
    typer.echo(f"stop_reason: {r.stop_reason.value}", err=True)
    typer.echo(format_summary(r.summary), err=True)
    typer.echo(f"session: {r.session.id} (log: {r.log_path})", err=True)
    if r.stop_reason == StopReason.BUDGET_EXCEEDED:
        tripped = (r.session.budget or {}).get("tripped")
        typer.echo(
            f"budget exceeded: {tripped} cap reached; resume with: cora resume {r.session.id}",
            err=True,
        )
    if r.stop_reason != StopReason.FINAL_ANSWER:
        raise typer.Exit(1)


def _one_shot(
    task: str,
    workdir: Path,
    config: Path | None,
    approval: str | None,
    max_iterations: int | None,
    max_cost: float | None,
    verbose: bool,
    check: str | None,
    delegate: bool = False,
    max_wall_s: float | None = None,
    max_tool_calls: int | None = None,
) -> None:
    agent: Agent | None = None
    manager: McpManager | None = None
    try:
        _, cfg = load_resolved(find_config(config), workdir)
        for w in unpriced_warnings(cfg):
            typer.echo(w, err=True)
        cfg = apply_agent_overrides(
            cfg,
            approval,
            max_iterations,
            max_cost,
            delegate=delegate,
            max_wall_s=max_wall_s,
            max_tool_calls=max_tool_calls,
        )
        for w in cfg.mcp.warnings:
            typer.echo(w, err=True)
        manager = McpManager(cfg.mcp, Path(workdir).resolve())
        policy = ApprovalPolicy(cfg.agent.approval, review=_stderr_review)
        agent = Agent(
            cfg,
            workdir,
            policy,
            on_event=_stderr_events(verbose),
            project_context=load_project_context(workdir).render(),
            mcp=manager,
        )
        force_delegate_visible(agent)
        _policy_notices(agent, cfg.agent.approval)
        r = run_interruptible(agent.run(task, check_command=check))
    except CoraError as e:
        typer.echo(f"error: {describe_provider_error(e)}", err=True)
        raise typer.Exit(2) from e
    except KeyboardInterrupt as e:
        sid = agent.current.id if agent is not None and agent.current is not None else "<id>"
        typer.echo(f"interrupted; resume with: cora resume {sid}", err=True)
        raise typer.Exit(130) from e
    finally:
        if manager is not None:
            manager.close()
    _emit_result(r)


def _start_repl(
    workdir: Path,
    config: Path | None,
    approval: str | None,
    max_iterations: int | None,
    max_cost: float | None,
    verbose: bool,
    delegate: bool = False,
    tui: bool | None = None,
    resume_id: str | None = None,
) -> None:
    try:
        opts = ReplOptions(
            Path(workdir).resolve(),
            find_config(config),
            approval,
            max_iterations,
            max_cost,
            verbose,
            delegate,
            resume_id=resume_id,
        )
        history = opts.workdir / ".cora" / "history"
        ui_cfg = load_config(opts.config_path).ui
        mode = choose_ui(tui, os.environ, ui_cfg.tui,
                         stdin_tty=sys.stdin.isatty(), stdout_tty=sys.stdout.isatty())
        if mode == "tui":
            from cora.cli.tui.app import run_tui

            code = run_tui(opts, history, ui_cfg)
        else:
            io = (PlainIO() if mode == "plain"
                  else TerminalIO(history, list(COMMANDS), workdir=opts.workdir))
            code = Repl(io, opts).run()
    except CoraError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    raise typer.Exit(code)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    print_: PrintOpt = None,
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    verbose: VerboseOpt = False,
    delegate: DelegateOpt = False,
    tui: TuiOpt = None,
    version: VersionOpt = False,
    headless: HeadlessOpt = False,
    json_: JsonOpt = False,
    quiet: QuietOpt = False,
    task_file: TaskFileOpt = None,
    max_wall_s: MaxWallOpt = None,
    max_tool_calls: MaxToolCallsOpt = None,
    resume_id: ResumeIdOpt = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if headless or json_ or quiet or task_file is not None or resume_id is not None or (
        print_ == "-"
    ):
        raise typer.Exit(run_headless(
            HeadlessOptions(
                task=print_,
                workdir=Path(workdir),
                config=config,
                task_file=task_file,
                headless=headless,
                json=json_,
                quiet=quiet,
                verbose=verbose,
                approval=approval,
                max_iterations=max_iterations,
                max_cost=max_cost,
                max_wall_s=max_wall_s,
                max_tool_calls=max_tool_calls,
                delegate=delegate,
                resume_id=resume_id,
            ),
            progress=_stderr_events(verbose),
            review=_stderr_review,
        ))
    if print_ is not None:
        _one_shot(
            print_,
            Path(workdir),
            config,
            approval,
            max_iterations,
            max_cost,
            verbose,
            None,
            delegate,
            max_wall_s,
            max_tool_calls,
        )
        return
    _start_repl(workdir, config, approval, max_iterations, max_cost, verbose, delegate, tui)


@app.command()
def run(
    task: Annotated[str | None, typer.Argument()] = None,
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    verbose: VerboseOpt = False,
    check: Annotated[str | None, typer.Option("--check")] = None,
    delegate: DelegateOpt = False,
    headless: HeadlessOpt = False,
    json_: JsonOpt = False,
    quiet: QuietOpt = False,
    task_file: TaskFileOpt = None,
    max_wall_s: MaxWallOpt = None,
    max_tool_calls: MaxToolCallsOpt = None,
    resume_id: ResumeIdOpt = None,
) -> None:
    if _wants_headless(task, headless, json_, quiet, task_file, resume_id):
        raise typer.Exit(run_headless(
            HeadlessOptions(
                task=task,
                workdir=Path(workdir),
                config=config,
                task_file=task_file,
                headless=headless,
                json=json_,
                quiet=quiet,
                verbose=verbose,
                approval=approval,
                max_iterations=max_iterations,
                max_cost=max_cost,
                max_wall_s=max_wall_s,
                max_tool_calls=max_tool_calls,
                check=check,
                delegate=delegate,
                resume_id=resume_id,
            ),
            progress=_stderr_events(verbose),
            review=_stderr_review,
        ))
    _one_shot(
        task, workdir, config, approval, max_iterations, max_cost, verbose, check, delegate,
        max_wall_s, max_tool_calls,
    )


@app.command(help="Interactive session (same as running `cora` with no arguments)")
def chat(
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    verbose: VerboseOpt = False,
    delegate: DelegateOpt = False,
    tui: TuiOpt = None,
) -> None:
    _start_repl(workdir, config, approval, max_iterations, max_cost, verbose, delegate, tui)


@app.command(help=(
    "Resume a saved session: on an interactive terminal open the TUI (or classic REPL with "
    "--no-tui) with the session loaded; otherwise continue it once, non-interactively"))
def resume(
    session_id: Annotated[str, typer.Argument()],
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    verbose: VerboseOpt = False,
    delegate: DelegateOpt = False,
    tui: TuiOpt = None,
) -> None:
    if interactive_terminal(os.environ, stdin_tty=sys.stdin.isatty(),
                            stdout_tty=sys.stdout.isatty()):
        _start_repl(workdir, config, approval, max_iterations, max_cost, verbose, delegate,
                    tui, resume_id=session_id)
        return
    agent: Agent | None = None
    manager: McpManager | None = None
    try:
        _, cfg = load_resolved(find_config(config), workdir)
        for w in unpriced_warnings(cfg):
            typer.echo(w, err=True)
        cfg = apply_agent_overrides(
            cfg, approval, max_iterations, max_cost, delegate=delegate
        )
        for w in cfg.mcp.warnings:
            typer.echo(w, err=True)
        manager = McpManager(cfg.mcp, Path(workdir).resolve())
        policy = ApprovalPolicy(cfg.agent.approval, review=_stderr_review)
        agent = Agent(
            cfg,
            workdir,
            policy,
            on_event=_stderr_events(verbose),
            project_context=load_project_context(workdir).render(),
            mcp=manager,
        )
        force_delegate_visible(agent)
        _policy_notices(agent, cfg.agent.approval)
        r = run_interruptible(agent.resume(session_id))
    except CoraError as e:
        typer.echo(f"error: {describe_provider_error(e)}", err=True)
        raise typer.Exit(2) from e
    except KeyboardInterrupt as e:
        sid = agent.current.id if agent is not None and agent.current is not None else "<id>"
        typer.echo(f"interrupted; resume with: cora resume {sid}", err=True)
        raise typer.Exit(130) from e
    finally:
        if manager is not None:
            manager.close()
    _emit_result(r)


def _split(s: str | None) -> list[str]:
    if s is None:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


BENCH_MISSING = (
    "error: the bench is not part of this installation; run it from a source checkout "
    "with `uv run cora bench ...`"
)


def _require_bench() -> None:
    try:
        importlib.import_module("cora.bench")
    except ModuleNotFoundError as e:
        if e.name != "cora.bench":
            raise
        typer.echo(BENCH_MISSING, err=True)
        raise typer.Exit(2) from None


def _live_progress(result: LiveTaskResult, spent: float) -> None:
    arm = f"{result.arm} " if result.arm else ""
    rep = f" r{result.repeat_index}" if result.repeat_index > 0 else ""
    score = f" score={result.score:.2f}" if result.score is not None else ""
    typer.echo(
        f"[bench] {result.task} {arm}{result.model} {result.protocol}{rep}: {result.status}"
        f"{score} cost=${result.cost_usd:.6f} spent=${spent:.6f}",
        err=True,
    )


@dataclasses.dataclass(frozen=True)
class _LiveSetup:
    model_ids: list[str]
    protocols: list[str]
    max_cost: float
    max_task_cost: float
    max_iterations: int
    arms: tuple[str, ...] | None
    tasks: list[LiveTask]


def _live_setup(
    cfg,
    *,
    models: str | None,
    protocols: str | None,
    tasks: str | None,
    ab: str | None,
    max_cost: float | None,
    max_task_cost: float | None,
    max_iterations: int | None,
    suite: str = "default",
    e2e_task_cost: float | None = None,
) -> _LiveSetup:
    from cora.bench.e2e import select_e2e_tasks
    from cora.bench.live import parse_arms
    from cora.bench.live_tasks import MULTI_TASKS, select_tasks

    b = cfg.bench
    model_ids = _split(models) or list(b.models)
    protos = _split(protocols) or list(b.protocols)
    arms: tuple[str, ...] | None = None
    if ab is not None:
        arms = parse_arms(ab)
        model_ids = _split(models) or list(b.models)[:1]
        protos = _split(protocols) or ["react"]
        if len(model_ids) != 1 or len(protos) != 1:
            raise ConfigError(
                "--ab compares arms on exactly one model and one protocol; pass one "
                "--models id and one --protocols value"
            )
    if suite == "e2e":
        selected: Sequence[LiveTask | E2ETask] = select_e2e_tasks(_split(tasks) or None)
    elif ab is not None:
        selected = select_tasks(_split(tasks) or None, default=MULTI_TASKS)
    else:
        selected = select_tasks(_split(tasks) or None)
    mc = max_cost if max_cost is not None else b.max_cost_usd
    if e2e_task_cost is not None:
        if suite != "e2e":
            raise ConfigError(
                "--e2e-task-cost applies only to --suite e2e; use --max-task-cost for the "
                "default suite"
            )
        if not (0 < e2e_task_cost <= mc):
            raise ConfigError(
                f"--e2e-task-cost {e2e_task_cost} must be > 0 and <= --max-cost {mc}"
            )
        selected = tuple(dataclasses.replace(t, cost_usd=e2e_task_cost) for t in selected)
    if suite == "e2e":
        iters = max_iterations or max(t.max_iterations for t in selected)
        if max_task_cost is not None:
            mtc = max_task_cost
        elif e2e_task_cost is not None:
            mtc = e2e_task_cost
        elif b.max_task_cost_usd is not None:
            mtc = b.max_task_cost_usd
        else:
            mtc = min(mc, max(t.cost_usd for t in selected))
    else:
        mtc = (
            max_task_cost
            if max_task_cost is not None
            else (b.max_task_cost_usd if b.max_task_cost_usd is not None else mc / 10)
        )
        iters = max_iterations or b.max_iterations
    if not model_ids:
        raise ConfigError("no bench models: pass --models or set [bench].models")
    return _LiveSetup(model_ids, protos, mc, mtc, iters, arms, list(selected))


bench_app = typer.Typer(
    add_completion=False,
    help=(
        "Benchmarks: `cora bench` runs tasks (--live: real calls); `cora bench plan` prints "
        "the maximum spend without any call; `cora bench compare REPORT` joins a report with "
        "a baseline"
    ),
)
app.add_typer(bench_app, name="bench")


@bench_app.callback(invoke_without_command=True)
def bench(
    ctx: typer.Context,
    config: ConfigOpt = None,
    baseline: Annotated[Path | None, typer.Option("--baseline")] = None,
    workdir: WorkdirOpt = ".",
    live: Annotated[
        bool, typer.Option("--live", help="Run real OpenRouter calls (costs money)")
    ] = False,
    models: Annotated[
        str | None,
        typer.Option("--models", help="Comma-separated model ids (default [bench].models)"),
    ] = None,
    protocols: Annotated[
        str | None, typer.Option("--protocols", help="Comma-separated: react,native")
    ] = None,
    tasks: Annotated[
        str | None, typer.Option("--tasks", help="Comma-separated live task ids")
    ] = None,
    max_cost: Annotated[
        float | None,
        typer.Option(
            "--max-cost",
            help="Total USD cap for this invocation (default 0.30, hard max 0.50)",
        ),
    ] = None,
    max_task_cost: Annotated[
        float | None,
        typer.Option("--max-task-cost", help="Per-task USD cap (default max-cost/10)"),
    ] = None,
    e2e_task_cost: Annotated[
        float | None,
        typer.Option(
            "--e2e-task-cost",
            help="--live --suite e2e: per-task USD cap that replaces task.toml limits.cost_usd "
            "(must be <= --max-cost; default: task.toml value)",
        ),
    ] = None,
    max_iterations: MaxIterationsOpt = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Report directory (default <workdir>/.cora/bench/live-<ts>)",
        ),
    ] = None,
    tool_groups: Annotated[
        str | None,
        typer.Option(
            "--tool-groups",
            help="Comma-separated tool groups exposed in --live runs (default: core = list_files, "
            "read_file, search, edit_file, run_shell; core always included; others: git, web, "
            "plan-todo, delegate)",
        ),
    ] = None,
    sensor: Annotated[
        bool,
        typer.Option(
            "--sensor",
            help="Opt-in for --live: run each task's own check before accepting a final answer "
            "(sensor gate, up to 3 retries) and enable the same-error tripwire; off by default "
            "for baseline comparability",
        ),
    ] = False,
    sensor_source: Annotated[
        str,
        typer.Option(
            "--sensor-source",
            help="With --live --sensor: oracle (each task's own check, default) or auto (the check "
            "command detected in the task workspace; the grader stays hidden)",
        ),
    ] = "oracle",
    verify_attempts: Annotated[
        int | None,
        typer.Option(
            "--verify-attempts",
            help="--live --suite e2e only: verified retry. After each final answer run the "
            "workspace's own visible check (auto-detected; the hidden grader is never used); "
            "on failure write one reflection and start a fresh attempt, up to N attempts in "
            "total (2-5). Not with --sensor. Cost cap and wall_s span all attempts",
        ),
    ] = None,
    ab: Annotated[
        str | None,
        typer.Option(
            "--ab",
            help="A/B arms on one cheap model (--live only): comma-separated deleg-off, "
            "deleg-on-par-off, deleg-on-par-on, strong-only, auto-routed, or 'all' (max 5); "
            "delegation x model combinations are not run",
        ),
    ] = None,
    repeats: RepeatsOpt = None,
    seed: SeedOpt = None,
    resume: Annotated[
        Path | None,
        typer.Option(
            "--resume",
            help="Continue the report in this directory (--live): completed runs are skipped",
        ),
    ] = None,
    trim_to_budget: Annotated[
        bool,
        typer.Option(
            "--trim-to-budget",
            help="--live: lower --repeats until the estimated maximum fits --max-cost",
        ),
    ] = False,
    suite: SuiteOpt = "default",
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    _require_bench()
    from cora.bench.e2e import load_e2e_tasks
    from cora.bench.harness import format_table, load_baseline, run_bench
    from cora.bench.live import (
        DEFAULT_BENCH_TOOL_GROUPS,
        DEFAULT_SEED,
        VERIFY_ATTEMPTS_MAX,
        VERIFY_ATTEMPTS_MIN,
        run_ab_bench,
        run_live_bench,
    )
    from cora.bench.live_tasks import ALL_TASK_IDS
    from cora.bench.plan import build_plan
    from cora.bench.report import (
        atomic_write_text,
        load_live_baseline,
        load_resume,
        report_json,
        report_markdown,
        scrub,
    )

    if suite not in ("default", "e2e"):
        typer.echo("error: --suite must be default or e2e", err=True)
        raise typer.Exit(2)
    if verify_attempts is not None and not live:
        typer.echo("error: --verify-attempts requires --live --suite e2e", err=True)
        raise typer.Exit(2)
    if verify_attempts is not None and suite != "e2e":
        typer.echo("error: --verify-attempts requires --suite e2e", err=True)
        raise typer.Exit(2)
    if verify_attempts is not None and sensor:
        typer.echo("error: --verify-attempts and --sensor are mutually exclusive", err=True)
        raise typer.Exit(2)
    if verify_attempts is not None and not (
        VERIFY_ATTEMPTS_MIN <= verify_attempts <= VERIFY_ATTEMPTS_MAX
    ):
        typer.echo("error: --verify-attempts must be an integer from 2 to 5", err=True)
        raise typer.Exit(2)
    if sensor_source not in ("oracle", "auto"):
        typer.echo("error: --sensor-source must be oracle or auto", err=True)
        raise typer.Exit(2)
    if sensor_source == "auto" and not (live and sensor):
        typer.echo("error: --sensor-source auto requires --live --sensor", err=True)
        raise typer.Exit(2)
    if suite == "e2e" and sensor and sensor_source != "auto":
        typer.echo(
            "error: --suite e2e --sensor needs --sensor-source auto (e2e tasks have no oracle "
            "check; the grader stays hidden)",
            err=True,
        )
        raise typer.Exit(2)
    if not live:
        live_only = [
            models,
            protocols,
            tasks,
            max_cost,
            max_task_cost,
            e2e_task_cost,
            max_iterations,
            out,
            tool_groups,
            ab,
            resume,
        ]
        if any(v is not None for v in live_only) or sensor or trim_to_budget or suite != "default":
            typer.echo(
                "error: --models/--protocols/--tasks/--max-cost/--max-task-cost/"
                "--e2e-task-cost/--max-iterations/--out/--tool-groups/--sensor/--ab/--resume/"
                "--trim-to-budget/--suite require --live",
                err=True,
            )
            raise typer.Exit(2)
        try:
            _, cfg = load_resolved(find_config(config), workdir)
            for w in unpriced_warnings(cfg):
                typer.echo(w, err=True)
            results = asyncio.run(
                run_bench(
                    cfg,
                    baseline=load_baseline(baseline) if baseline else None,
                    repeats=repeats or 1,
                    seed=DEFAULT_SEED if seed is None else seed,
                )
            )
        except CoraError as e:
            typer.echo(f"error: {describe_provider_error(e)}", err=True)
            raise typer.Exit(2) from e
        typer.echo(format_table(results))
        return
    secrets: list[str] = []
    try:
        _, cfg = load_resolved(find_config(config), workdir)
        for w in unpriced_warnings(cfg):
            typer.echo(w, err=True)
        setup = _live_setup(
            cfg,
            models=models,
            protocols=protocols,
            tasks=tasks,
            ab=ab,
            max_cost=max_cost,
            max_task_cost=max_task_cost,
            max_iterations=max_iterations,
            suite=suite,
            e2e_task_cost=e2e_task_cost,
        )
        b = cfg.bench
        mc = setup.max_cost
        reps = repeats or 1
        base_seed = DEFAULT_SEED if seed is None else seed
        secrets = [v for n in secret_env_names(cfg) if (v := os.environ.get(n))]

        def notice(msg: str) -> None:
            typer.echo(f"[bench] {scrub(msg, secrets)}", err=True)

        base = (
            load_live_baseline(
                baseline, list(ALL_TASK_IDS) + [t.id for t in load_e2e_tasks()]
            )
            if baseline
            else None
        )
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_dir = out or Path(workdir) / ".cora" / "bench" / f"live-{stamp}"
        prior: dict[str, LiveTaskResult] | None = None
        prior_costs: dict[UnitKey, list[float]] | None = None
        if resume is not None:
            if out is not None and out.resolve() != resume.resolve():
                raise ConfigError(
                    "--resume writes back into its directory; do not pass a different --out"
                )
            out_dir = resume
            prior_obj, prior = load_resume(resume)
            prior_seed = prior_obj.get("settings", {}).get("seed", DEFAULT_SEED)
            if prior_seed != base_seed:
                raise ConfigError(
                    f"--resume: the report used --seed {prior_seed}; pass the same --seed"
                )
            shutil.copyfile(resume / "report.json", resume / "report.resume-backup.json")
            prior_costs = {}
            for r in prior.values():
                prior_costs.setdefault((r.arm, r.model, r.protocol, r.task), []).append(
                    r.cost_usd
                )
            notice(f"resume: reusing {len(prior)} completed run(s)")

        def make_plan(n: int) -> BudgetPlan:
            return build_plan(
                cfg,
                tasks=setup.tasks,
                models=setup.model_ids,
                protocols=setup.protocols,
                arms=setup.arms,
                max_iterations=setup.max_iterations,
                max_task_cost_usd=setup.max_task_cost,
                max_cost_usd=mc,
                repeats=n,
                prior=prior_costs,
            )

        plan = make_plan(reps)
        enforce = repeats is not None or trim_to_budget or resume is not None
        trimmed: dict | None = None
        if plan.exceeds:
            if trim_to_budget:
                r = plan.suggest_repeats()
                if r is None or r < 1:
                    typer.echo(
                        f"error: even --repeats 1 is estimated at ${plan.total_at(1):.6f} > "
                        f"--max-cost ${mc:g}; nothing was called",
                        err=True,
                    )
                    raise typer.Exit(2)
                trimmed = {
                    "requested_repeats": reps,
                    "used_repeats": r,
                    "estimated_max_usd_before": plan.total_usd,
                    "estimated_max_usd_after": plan.total_at(r),
                    "max_cost_usd": mc,
                }
                reps = r
                plan = make_plan(reps)
                notice(f"trimmed --repeats to {r} to fit --max-cost")
            elif enforce:
                typer.echo(
                    f"error: estimated maximum cost ${plan.total_usd:.6f} for {plan.runs} runs "
                    f"exceeds --max-cost ${mc:g}; nothing was called. Lower --repeats, pass "
                    "--trim-to-budget, or check `cora bench plan`.",
                    err=True,
                )
                raise typer.Exit(2)
            else:
                notice(
                    f"note: estimated maximum ${plan.total_usd:.6f} exceeds --max-cost ${mc:g}; "
                    "the running budget skips runs once the cap is reached (see `cora bench plan`)"
                )
        out_dir.mkdir(parents=True, exist_ok=True)
        extras = {
            "budget_plan": plan.to_dict(),
            "trimmed": trimmed,
            "resumed": {"reused_runs": len(prior)} if prior is not None else None,
        }

        def checkpoint(rep: LiveReport) -> None:
            atomic_write_text(
                out_dir / "report.json",
                report_json(rep, base, secrets, include_aggregation=False),
            )

        if setup.arms is not None:
            report = asyncio.run(
                run_ab_bench(
                    cfg,
                    arms=setup.arms,
                    model=setup.model_ids[0],
                    protocol=setup.protocols[0],
                    tasks=setup.tasks,
                    max_cost_usd=mc,
                    max_task_cost_usd=setup.max_task_cost,
                    max_iterations=setup.max_iterations,
                    state_dir=out_dir / "state",
                    on_progress=_live_progress,
                    tool_groups=_split(tool_groups) or list(DEFAULT_BENCH_TOOL_GROUPS),
                    sensor=sensor,
                    sensor_source=sensor_source,
                    verify_attempts=verify_attempts,
                    on_notice=notice,
                    stall_threshold_s=b.stall_threshold_s,
                    repeats=reps,
                    seed=base_seed,
                    prior=prior,
                    on_checkpoint=checkpoint,
                    report_extras=extras,
                )
            )
        else:
            report = asyncio.run(
                run_live_bench(
                    cfg,
                    models=setup.model_ids,
                    protocols=setup.protocols,
                    tasks=setup.tasks,
                    max_cost_usd=mc,
                    max_task_cost_usd=setup.max_task_cost,
                    max_iterations=setup.max_iterations,
                    state_dir=out_dir / "state",
                    on_progress=_live_progress,
                    tool_groups=_split(tool_groups) or list(DEFAULT_BENCH_TOOL_GROUPS),
                    sensor=sensor,
                    sensor_source=sensor_source,
                    verify_attempts=verify_attempts,
                    on_notice=notice,
                    stall_threshold_s=b.stall_threshold_s,
                    repeats=reps,
                    seed=base_seed,
                    prior=prior,
                    on_checkpoint=checkpoint,
                    report_extras=extras,
                )
            )
        atomic_write_text(out_dir / "report.json", report_json(report, base, secrets))
        markdown = report_markdown(report, base, secrets)
        atomic_write_text(out_dir / "report.md", markdown)
        typer.echo(markdown)
        typer.echo(f"report: {out_dir}", err=True)
        if report.aborted is not None:
            msg = (
                f"error: live bench aborted: {scrub(report.aborted, secrets)}; "
                f"partial report written to {out_dir}"
            )
            if report.abort_guidance:
                msg += "\n" + scrub(report.abort_guidance, secrets)
            typer.echo(msg, err=True)
            raise typer.Exit(3)
    except CoraError as e:
        typer.echo(f"error: {scrub(describe_provider_error(e), secrets)}", err=True)
        raise typer.Exit(2) from e


@bench_app.command(
    "plan",
    help="Print the maximum spend for a bench configuration without any call (no key or "
    "network needed)",
)
def bench_plan(
    config: ConfigOpt = None,
    workdir: WorkdirOpt = ".",
    models: Annotated[str | None, typer.Option("--models")] = None,
    protocols: Annotated[str | None, typer.Option("--protocols")] = None,
    tasks: Annotated[str | None, typer.Option("--tasks")] = None,
    ab: Annotated[str | None, typer.Option("--ab")] = None,
    repeats: RepeatsOpt = None,
    max_cost: MaxCostOpt = None,
    max_task_cost: Annotated[float | None, typer.Option("--max-task-cost")] = None,
    e2e_task_cost: Annotated[
        float | None,
        typer.Option(
            "--e2e-task-cost",
            help="per-task USD cap replacing task.toml limits.cost_usd (--suite e2e)",
        ),
    ] = None,
    max_iterations: MaxIterationsOpt = None,
    suite: SuiteOpt = "default",
) -> None:
    _require_bench()
    from cora.bench.plan import build_plan, plan_markdown

    if suite not in ("default", "e2e"):
        typer.echo("error: --suite must be default or e2e", err=True)
        raise typer.Exit(2)
    try:
        _, cfg = load_resolved(find_config(config), workdir)
        setup = _live_setup(
            cfg,
            models=models,
            protocols=protocols,
            tasks=tasks,
            ab=ab,
            max_cost=max_cost,
            max_task_cost=max_task_cost,
            max_iterations=max_iterations,
            suite=suite,
            e2e_task_cost=e2e_task_cost,
        )
        plan = build_plan(
            cfg,
            tasks=setup.tasks,
            models=setup.model_ids,
            protocols=setup.protocols,
            arms=setup.arms,
            max_iterations=setup.max_iterations,
            max_task_cost_usd=setup.max_task_cost,
            max_cost_usd=setup.max_cost,
            repeats=repeats or 1,
        )
    except CoraError as e:
        typer.echo(f"error: {describe_provider_error(e)}", err=True)
        raise typer.Exit(2) from e
    typer.echo(plan_markdown(plan))


@bench_app.command(
    "compare", help="Join a bench report.json with a baseline.toml by task id (no calls)"
)
def bench_compare(
    report: Annotated[Path, typer.Argument(help="report.json from cora bench --live")],
    baseline: Annotated[
        Path | None,
        typer.Option(
            "--baseline",
            help="baseline.toml (schema in USAGE.md); a missing file prints absolute "
            "numbers only",
        ),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out", help="Also write compare.md and compare.json into this directory"
        ),
    ] = None,
) -> None:
    _require_bench()
    from cora.bench.compare import (
        compare,
        compare_markdown,
        known_task_ids,
        load_compare_baseline,
        load_report_runs,
    )
    from cora.bench.report import atomic_write_text

    try:
        obj, runs = load_report_runs(report)
        notes: list[str] = []
        base = None
        if baseline is not None:
            if baseline.is_file():
                base = load_compare_baseline(baseline, known_task_ids())
            else:
                notes.append(f"baseline file not found: {baseline.name}")
        cmp = compare(obj, runs, base, report.name, notes)
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    for warning in cmp["warnings"]:
        typer.echo(warning, err=True)
    md = compare_markdown(cmp)
    typer.echo(md)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out / "compare.md", md)
        atomic_write_text(out / "compare.json", json.dumps(cmp, indent=2, ensure_ascii=False))


@app.command(
    help=(
        "Decider tools: `cora decider eval --cases FILE` measures agreement and "
        "expected cost offline"
    )
)
def decider(
    action: Annotated[str, typer.Argument(help="Action: eval")],
    cases: Annotated[
        Path | None, typer.Option("--cases", help="JSONL case file (one case per line)")
    ] = None,
    decider_kind: Annotated[
        str,
        typer.Option("--decider", help="heuristic | replay | llm (llm needs --live)"),
    ] = "heuristic",
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Opt-in for --decider llm: real OpenRouter calls (costs money)",
        ),
    ] = False,
    max_cost: Annotated[
        float | None,
        typer.Option(
            "--max-cost",
            help="--decider llm: total USD cap (default 0.05, hard max 0.50)",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="--decider llm: tier name or [[models]] id (default [decider].model)",
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON")] = False,
    config: ConfigOpt = None,
    workdir: WorkdirOpt = ".",
) -> None:
    _require_bench()
    from cora.bench.decider_eval import (
        DEFAULT_EVAL_MAX_COST_USD,
        EVAL_DECIDERS,
        eval_json,
        format_eval,
        load_cases,
        run_decider_eval,
    )
    from cora.bench.report import scrub

    if action != "eval":
        typer.echo(f"error: unknown action '{action}'; expected: eval", err=True)
        raise typer.Exit(2)
    if cases is None:
        typer.echo("error: --cases FILE is required", err=True)
        raise typer.Exit(2)
    if decider_kind not in EVAL_DECIDERS:
        typer.echo("error: --decider must be one of heuristic, replay, llm", err=True)
        raise typer.Exit(2)
    if decider_kind != "llm" and (live or max_cost is not None or model is not None):
        typer.echo("error: --live/--max-cost/--model require --decider llm", err=True)
        raise typer.Exit(2)
    if decider_kind == "llm" and not live:
        typer.echo(
            "--decider llm makes real OpenRouter calls and costs money; nothing was called. "
            "Re-run with --live to opt in (optional --max-cost, default 0.05 USD).",
            err=True,
        )
        raise typer.Exit(2)
    secrets: list[str] = []
    try:
        _, cfg = load_resolved(find_config(config), workdir)
        if model is not None:
            check_decider_model(model, cfg.models)
            cfg = dataclasses.replace(cfg, decider=dataclasses.replace(cfg.decider, model=model))
        loaded = load_cases(cases)
        secrets = [v for n in secret_env_names(cfg) if (v := os.environ.get(n))]
        report = asyncio.run(
            run_decider_eval(
                cfg,
                loaded,
                decider_kind,
                max_cost_usd=max_cost if max_cost is not None else DEFAULT_EVAL_MAX_COST_USD,
                on_notice=lambda m: typer.echo(f"[decider] {scrub(m, secrets)}", err=True),
            )
        )
    except CoraError as e:
        typer.echo(f"error: {scrub(describe_provider_error(e), secrets)}", err=True)
        raise typer.Exit(2) from e
    typer.echo(eval_json(report) if as_json else format_eval(report))
    if report.aborted:
        msg = f"error: decider eval aborted: {scrub(report.aborted, secrets)}"
        if report.abort_guidance:
            msg += "\n" + scrub(report.abort_guidance, secrets)
        typer.echo(msg, err=True)
        raise typer.Exit(3)


@app.command(
    name="sale",
    help=(
        "Experimental, not wired into the agent: SALE-lite routing (offline). "
        "`cora sale eval --cases FILE` compares always-cheap, always-strong, heuristic-router "
        "and SALE-lite bids on a tier table"
    ),
)
def sale_cmd(
    action: Annotated[str, typer.Argument(help="Action: eval")],
    cases: Annotated[
        Path | None, typer.Option("--cases", help="JSONL case file (one case per line)")
    ] = None,
    tiers: Annotated[
        Path | None,
        typer.Option(
            "--tiers",
            help="Tier table TOML (default [sale].tiers_file or the "
            "built-in M15-measured table)",
        ),
    ] = None,
    reward: Annotated[
        float | None,
        typer.Option("--reward", help="Task reward in cost units (default [sale].reward)"),
    ] = None,
    budget_cap: Annotated[
        float | None,
        typer.Option("--budget-cap", help="Per-task cost cap (default [sale].budget_cap)"),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON")] = False,
    config: ConfigOpt = None,
) -> None:
    _require_bench()
    from cora.bench.sale_eval import (
        format_sale_eval,
        load_sale_cases,
        run_sale_eval,
        sale_eval_json,
    )

    if action != "eval":
        typer.echo(f"error: unknown action '{action}'; expected: eval", err=True)
        raise typer.Exit(2)
    if cases is None:
        typer.echo("error: --cases FILE is required", err=True)
        raise typer.Exit(2)
    for flag, value in (("--reward", reward), ("--budget-cap", budget_cap)):
        if value is not None and not (math.isfinite(value) and value > 0):
            typer.echo(f"error: {flag} must be a number > 0", err=True)
            raise typer.Exit(2)
    try:
        cfg = load_config(find_config(config))
        s = cfg.sale
        table_path = tiers if tiers is not None else (Path(s.tiers_file) if s.tiers_file else None)
        table = load_tier_table(table_path)
        loaded = load_sale_cases(cases, table)
        report = run_sale_eval(
            loaded,
            table,
            reward=reward if reward is not None else s.reward,
            budget_cap=budget_cap if budget_cap is not None else s.budget_cap,
            router_threshold=cfg.router.threshold,
        )
    except CoraError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    typer.echo(sale_eval_json(report) if as_json else format_sale_eval(report))


@app.command(
    name="mcp",
    help="MCP: `cora mcp list` starts each configured server briefly, lists its tools and "
    "stops it; `cora mcp serve` runs CORA itself as an MCP stdio server (tools run_task, "
    "resume_session, list_sessions)",
)
def mcp_cmd(
    action: Annotated[str, typer.Argument(help="Action: list | serve")],
    config: ConfigOpt = None,
    workdir: WorkdirOpt = ".",
) -> None:
    if action == "serve":
        raise typer.Exit(mcp_serve(config, Path(workdir)))
    if action != "list":
        typer.echo(f"error: unknown action '{action}'; expected: list or serve", err=True)
        raise typer.Exit(2)
    try:
        _, cfg = load_resolved(find_config(config), workdir)
    except CoraError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2) from e
    for w in cfg.mcp.warnings:
        typer.echo(w, err=True)
    if not cfg.mcp.servers:
        typer.echo(MCP_NONE)
        return
    manager = McpManager(cfg.mcp, Path(workdir).resolve())
    try:
        statuses = manager.probe_all()
    finally:
        manager.close()
    typer.echo("MCP servers:")
    for st in statuses:
        if st.state == "running":
            typer.echo(f"  {st.name}  ok  {len(st.tools)} tools")
            for t in st.tools:
                first = (t.description.splitlines() or [""])[0][:80]
                typer.echo(f"    {t.name}  {first}")
        elif st.state == "disabled":
            typer.echo(f"  {st.name}  disabled  (enabled = false)")
        else:
            typer.echo(f"  {st.name}  failed  {st.last_error or 'unknown error'}")
        for note in st.notes:
            typer.echo(f"    note: {note}")


project_app = typer.Typer(
    add_completion=False,
    help=(
        "Milestone projects: `cora project plan GOAL -o PLAN.toml` writes a milestone plan from "
        "a goal (runs nothing); `cora project run PLAN.toml` (or `cora project run --goal GOAL`) "
        "runs a plan with a checkpoint per milestone; `cora project resume RUN_ID` continues it"
    ),
)
app.add_typer(project_app, name="project")


@project_app.command(
    name="run",
    help="Run the milestones of a TOML plan in order, checkpointing after each",
)
def project_run(
    plan: Annotated[
        Path | None, typer.Argument(help="Plan file (TOML); omit when using --goal")
    ] = None,
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    max_wall_s: MaxWallOpt = None,
    max_tool_calls: MaxToolCallsOpt = None,
    headless: HeadlessOpt = False,
    json_: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
    goal: Annotated[
        str | None,
        typer.Option("--goal", help="Plan the project from GOAL with the model, then run it"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o",
            help="With --goal: also write the generated plan to this file",
        ),
    ] = None,
) -> None:
    raise typer.Exit(run_project(
        ProjectOptions(
            workdir=Path(workdir),
            config=config,
            plan=plan,
            headless=headless,
            json=json_,
            quiet=quiet,
            verbose=verbose,
            approval=approval,
            max_iterations=max_iterations,
            max_cost=max_cost,
            max_wall_s=max_wall_s,
            max_tool_calls=max_tool_calls,
            goal=goal,
            output=output,
        ),
        progress=_stderr_events(verbose),
        review=_stderr_review,
    ))


@project_app.command(
    name="plan",
    help="Ask the model to split GOAL into a milestone plan and write it as TOML (runs nothing)",
)
def project_plan(
    goal: Annotated[str, typer.Argument(help="Project goal")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Plan file to write (TOML)")
    ] = None,
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    max_cost: MaxCostOpt = None,
    json_: JsonOpt = False,
    quiet: QuietOpt = False,
    approval: ApprovalOpt = None,
) -> None:
    raise typer.Exit(run_plan(PlanOptions(
        goal=goal, output=output, workdir=Path(workdir), config=config,
        json=json_, quiet=quiet, max_cost=max_cost, approval=approval,
    )))


@project_app.command(
    name="resume",
    help="Resume a project run from its checkpoint; completed milestones are skipped",
)
def project_resume(
    run_id: Annotated[str, typer.Argument(help="Run id printed by `cora project run`")],
    workdir: WorkdirOpt = ".",
    config: ConfigOpt = None,
    approval: ApprovalOpt = None,
    max_iterations: MaxIterationsOpt = None,
    max_cost: MaxCostOpt = None,
    max_wall_s: MaxWallOpt = None,
    max_tool_calls: MaxToolCallsOpt = None,
    headless: HeadlessOpt = False,
    json_: JsonOpt = False,
    quiet: QuietOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    raise typer.Exit(run_project(
        ProjectOptions(
            workdir=Path(workdir),
            config=config,
            run_id=run_id,
            headless=headless,
            json=json_,
            quiet=quiet,
            verbose=verbose,
            approval=approval,
            max_iterations=max_iterations,
            max_cost=max_cost,
            max_wall_s=max_wall_s,
            max_tool_calls=max_tool_calls,
        ),
        progress=_stderr_events(verbose),
        review=_stderr_review,
    ))


if __name__ == "__main__":
    app()
