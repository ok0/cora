from __future__ import annotations

import asyncio
import dataclasses
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cora.bench import e2e
from cora.bench.e2e import E2ETask
from cora.bench.live_tasks import (
    DIFFICULTY_THRESHOLDS,
    LIVE_TASKS,
    MULTI_TASKS,
    LiveTask,
    write_task_files,
)
from cora.bench.plan import task_limits
from cora.bench.preflight import run_preflight
from cora.bench.report import AB_ARMS, LiveReport, LiveTaskResult, make_run_id, scrub
from cora.core.agent import Agent
from cora.core.checks import detect_check_command
from cora.core.config import (
    BENCH_PROTOCOLS,
    AgentSettings,
    CoraConfig,
    ModelSpec,
    ToolGroupSettings,
    apply_pin,
    find_model,
    secret_env_names,
)
from cora.core.errors import (
    ConfigError,
    ProviderAccountError,
    ProviderError,
    describe_provider_error,
)
from cora.core.metering import CostMeter
from cora.core.policy import PolicyGate, PolicySettings
from cora.core.providers import ProviderPool
from cora.core.router import HeuristicRouter
from cora.core.state import StopReason
from cora.core.toolgroups import GROUPS, OPTIONAL_GROUPS, group_of
from cora.core.tools import ApprovalPolicy, ApprovalRequest, default_tools

HARD_MAX_COST_USD = 0.50
CHECK_TIMEOUT_S = 60
SENSOR_SOURCES = ("oracle", "auto")
DEFAULT_BENCH_TOOL_GROUPS: tuple[str, ...] = ("core",)
VERIFY_ATTEMPTS_MIN = 2
VERIFY_ATTEMPTS_MAX = 5
DEFAULT_SEED = 0
_CLOCK_ID = getattr(time, "CLOCK_BOOTTIME", None)
if _CLOCK_ID is None:
    _CLOCK_ID = getattr(time, "CLOCK_MONOTONIC", None)
ABORT_LABELS = {
    401: "API key rejected",
    402: "insufficient credits",
    403: "key forbidden or key limit reached",
}


def validate_verify_attempts(
    n: int | None, *, sensor: bool, tasks: Sequence[LiveTask | E2ETask]
) -> None:
    if n is None:
        return
    if (
        isinstance(n, bool)
        or not isinstance(n, int)
        or not VERIFY_ATTEMPTS_MIN <= n <= VERIFY_ATTEMPTS_MAX
    ):
        raise ConfigError("--verify-attempts must be an integer from 2 to 5")
    if sensor:
        raise ConfigError("--verify-attempts and --sensor are mutually exclusive")
    if not tasks or not all(isinstance(t, E2ETask) for t in tasks):
        raise ConfigError("--verify-attempts requires --suite e2e")


def bench_clock() -> float:
    """Monotonic seconds that keep counting while the machine sleeps.

    time.monotonic() on macOS (mach_absolute_time) stops during sleep and under-counted
    bench latency; clock_gettime(CLOCK_MONOTONIC) on macOS / CLOCK_BOOTTIME on Linux do not.
    """
    if _CLOCK_ID is None:
        return time.time()
    return time.clock_gettime(_CLOCK_ID)


class BenchAborted(ProviderError): ...


class _CallTracker:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.latencies: list[float] = []
        self.abort_reason: str | None = None
        self.abort_error: ProviderAccountError | None = None

    def begin_cell(self) -> None:
        self.latencies = []


class _TrackedProvider:
    def __init__(self, inner, tracker: _CallTracker) -> None:
        self._inner = inner
        self._tracker = tracker

    async def complete(self, request):
        t = self._tracker
        if t.abort_reason is not None:
            raise BenchAborted(f"bench aborted: {t.abort_reason}")
        started = t.clock()
        try:
            return await self._inner.complete(request)
        except ProviderAccountError as e:
            if t.abort_reason is None:
                t.abort_reason = (
                    f"HTTP {e.status} from the provider "
                    f"({ABORT_LABELS.get(e.status, 'account error')})"
                )
                t.abort_error = e
            raise
        finally:
            t.latencies.append(max(0.0, t.clock() - started))


class _TrackedPool:
    def __init__(self, inner, tracker: _CallTracker) -> None:
        self._inner = inner
        self._tracker = tracker
        self._wrapped: dict[str, _TrackedProvider] = {}

    def get(self, name: str) -> _TrackedProvider:
        if name not in self._wrapped:
            self._wrapped[name] = _TrackedProvider(self._inner.get(name), self._tracker)
        return self._wrapped[name]


def _abort_guidance(tracker: _CallTracker) -> str | None:
    e = tracker.abort_error
    return describe_provider_error(e) if e is not None else None


def _account_targets(
    pool, used: Sequence[ModelSpec], account: Mapping[str, Any] | None
) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    for spec in used:
        name = spec.provider
        if name in targets:
            continue
        if account is not None and name in account:
            targets[name] = account[name]
            continue
        try:
            targets[name] = pool.get(name)
        except KeyError:
            targets[name] = None
    return targets


async def _preflight(
    pool, used: Sequence[ModelSpec], account: Mapping[str, Any] | None, run_cap: float,
    on_notice: Callable[[str], None] | None,
) -> None:
    result = await run_preflight(_account_targets(pool, used, account), run_cap)
    if on_notice is not None:
        for line in result.notices:
            on_notice(line)


class Budget:
    def __init__(self, max_total: float, max_task: float) -> None:
        self.max_total = max_total
        self.max_task = max_task
        self.task_cap = max_task
        self.spent_total = 0.0
        self.tripped: str | None = None
        self.exhausted = False

    def begin_task(self, max_task: float | None = None) -> None:
        self.tripped = None
        self.task_cap = self.max_task if max_task is None else min(max_task, self.max_task)

    def gate(self, task_spent: float, projected: float) -> bool:
        if task_spent + projected > self.task_cap:
            self.tripped = "task"
            return False
        if self.spent_total + task_spent + projected > self.max_total:
            self.tripped = "total"
            return False
        return True

    def settle(self, task_cost: float) -> None:
        self.spent_total += task_cost
        if self.tripped == "total" or self.spent_total >= self.max_total:
            self.exhausted = True


def validate_live_options(
    config: CoraConfig,
    models: Sequence[str],
    protocols: Sequence[str],
    max_cost_usd: float,
    max_task_cost_usd: float,
    max_iterations: int,
) -> list[ModelSpec]:
    if not models:
        raise ConfigError("no bench models: pass --models or set [bench].models")
    specs: list[ModelSpec] = []
    for model_id in models:
        spec = next((m for m in config.models if m.id == model_id), None)
        if spec is None:
            raise ConfigError(
                f"model '{model_id}' is not in the model catalog ([[models]] in cora.toml); "
                "add it with prices"
            )
        if not spec.price_known:
            raise ConfigError(
                f"model '{model_id}' has no known price; the live bench refuses unpriced "
                "models (add input/output prices to [[models]])"
            )
        if spec not in specs:
            specs.append(spec)
    if not protocols or any(p not in BENCH_PROTOCOLS for p in protocols):
        raise ConfigError(f"protocols must be a non-empty subset of {list(BENCH_PROTOCOLS)}")
    if not (0 < max_cost_usd <= HARD_MAX_COST_USD):
        raise ConfigError(
            f"--max-cost {max_cost_usd} must be > 0 and <= {HARD_MAX_COST_USD} "
            "(hard per-invocation limit)"
        )
    if not (0 < max_task_cost_usd <= max_cost_usd):
        raise ConfigError(
            f"--max-task-cost {max_task_cost_usd} must be > 0 and <= --max-cost {max_cost_usd}"
        )
    if max_iterations < 1:
        raise ConfigError("--max-iterations must be >= 1")
    return specs


def normalize_tool_groups(groups: Sequence[str]) -> tuple[str, ...]:
    bad = [g for g in groups if g not in GROUPS]
    if bad:
        raise ConfigError(f"unknown tool group(s) {bad}; expected values from {list(GROUPS)}")
    return ("core", *[g for g in dict.fromkeys(groups) if g != "core"])


def bench_tool_names(groups: Sequence[str]) -> list[str]:
    return [t.name for t in default_tools() if group_of(t.name) in groups]


def parse_arms(text: str) -> tuple[str, ...]:
    names = [x.strip() for x in text.split(",") if x.strip()]
    if names == ["all"]:
        return AB_ARMS
    return normalize_arms(names)


def normalize_arms(arms: Sequence[str]) -> tuple[str, ...]:
    if not arms:
        raise ConfigError("--ab needs at least one arm")
    for a in arms:
        if a not in AB_ARMS:
            raise ConfigError(
                f"unknown A/B arm '{a}'; expected 'all' or values from {list(AB_ARMS)} "
                "(delegation x model combinations are not run)"
            )
    chosen = set(arms)
    return tuple(a for a in AB_ARMS if a in chosen)


def _model_meta(spec: ModelSpec) -> dict:
    return {
        "id": spec.id,
        "provider": spec.provider,
        "input_usd_per_mtok": spec.input_usd_per_mtok,
        "output_usd_per_mtok": spec.output_usd_per_mtok,
        "supports_tools": spec.supports_tools,
    }


def _skipped(
    task: LiveTask, model_id: str, protocol: str, arm: str | None = None
) -> LiveTaskResult:
    return LiveTaskResult(
        task=task.id,
        kind=task.kind,
        model=model_id,
        protocol=protocol,
        status="skipped_budget",
        budget_reason="total",
        stop_reason=None,
        iterations=0,
        calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        provider_cost_calls=0,
        latency_s=0.0,
        detail="",
        arm=arm,
        difficulty=task.difficulty,
        estimated_minutes=task.estimated_minutes,
    )


def _not_run(
    task: LiveTask, model_id: str, protocol: str, arm: str | None = None
) -> LiveTaskResult:
    return dataclasses.replace(
        _skipped(task, model_id, protocol, arm),
        status="not_run",
        budget_reason=None,
        detail="not run: bench aborted",
    )


async def _run_cell(
    tracker: _CallTracker, run: Awaitable[LiveTaskResult]
) -> LiveTaskResult:
    tracker.begin_cell()
    started = tracker.clock()
    result = await run
    return dataclasses.replace(
        result,
        latency_s=max(0.0, tracker.clock() - started),
        call_latencies_s=[round(v, 3) for v in tracker.latencies],
    )


def _deleg_fields(summary: dict) -> dict:
    d = summary.get("delegated", {})
    return {
        "deleg_invocations": d.get("invocations", 0),
        "deleg_attempts": d.get("attempts", 0),
        "deleg_attempts_unparsed": d.get("attempts_unparsed", 0),
        "deleg_explore": d.get("explore_calls", 0),
        "deleg_general": d.get("general_calls", 0),
        "deleg_ok": d.get("ok", 0),
        "deleg_failed": d.get("failed", 0),
        "deleg_refused": d.get("refused", 0),
        "deleg_input_tokens": d.get("input_tokens", 0),
        "deleg_output_tokens": d.get("output_tokens", 0),
        "deleg_cost_usd": d.get("cost_usd", 0.0),
        "deleg_wall_s": d.get("wall_s", 0.0),
        "deleg_max_fanout": d.get("max_fanout", 0),
        "deleg_avoided_tokens_est": d.get("avoided_tokens_est", 0),
    }


def _arm_config(
    config: CoraConfig,
    arm: str,
    cheap: ModelSpec,
    strong: ModelSpec | None,
    protocol: str,
    max_iterations: int,
    max_task_cost: float,
    tool_groups: Sequence[str],
    sensor: bool,
    verify_attempts: int | None = None,
) -> CoraConfig:
    groups = (
        normalize_tool_groups([*tool_groups, "delegate"])
        if arm.startswith("deleg-on")
        else tuple(tool_groups)
    )
    pin = strong.id if arm == "strong-only" and strong is not None else cheap.id
    cfg = _run_config(
        config,
        pin,
        protocol,
        max_iterations,
        max_task_cost,
        groups,
        sensor=sensor,
        verify_attempts=verify_attempts,
    )
    if arm == "auto-routed":
        models = tuple(
            sorted(
                (m for m in cfg.models if m.source != "pin"),
                key=lambda m: m.id != cheap.id,
            )
        )
        cfg = dataclasses.replace(
            cfg, models=models, router=dataclasses.replace(cfg.router, pin=None)
        )
    if arm.startswith("deleg-on"):
        cfg = dataclasses.replace(
            cfg,
            delegation=dataclasses.replace(
                cfg.delegation, enabled=True, parallel_explore=(arm == "deleg-on-par-on")
            ),
        )
    return cfg


def _run_config(
    config: CoraConfig,
    model_id: str,
    protocol: str,
    max_iterations: int,
    max_task_cost: float,
    tool_groups: Sequence[str] = DEFAULT_BENCH_TOOL_GROUPS,
    sensor: bool = False,
    verify_attempts: int | None = None,
) -> CoraConfig:
    cfg = apply_pin(config, model_id)
    models = tuple(dataclasses.replace(m, tool_protocol=None) for m in cfg.models)
    return dataclasses.replace(
        cfg,
        models=models,
        agent=dataclasses.replace(
            cfg.agent,
            approval="auto",
            max_iterations=max_iterations,
            max_attempts=1 if verify_attempts is None else verify_attempts,
            max_cost_usd=max_task_cost,
            tool_protocol=protocol,
            tripwire=sensor,
            sensor_max_retries=AgentSettings().sensor_max_retries,
            sensor_feedback_chars=AgentSettings().sensor_feedback_chars,
            auto_check=verify_attempts is not None,
            selftest=False,
        ),
        delegation=dataclasses.replace(cfg.delegation, enabled=False),
        tool_groups=ToolGroupSettings(
            disabled=tuple(g for g in OPTIONAL_GROUPS if g not in tool_groups),
            auto_simple=False,
        ),
    )


def task_check_command(task: LiveTask) -> str:
    return task.check.format(python=shlex.quote(sys.executable))


def auto_check_command(task: LiveTask) -> str | None:
    with tempfile.TemporaryDirectory(prefix="cora-detect-") as tmp:
        write_task_files(Path(tmp), task.files)
        return detect_check_command(Path(tmp))


def auto_check_command_e2e(task: E2ETask) -> str | None:
    with tempfile.TemporaryDirectory(prefix="cora-detect-") as tmp:
        ws = e2e.prepare_workspace(task, Path(tmp))
        return detect_check_command(ws)


def _auto_check(task: LiveTask | E2ETask) -> str | None:
    if isinstance(task, E2ETask):
        return auto_check_command_e2e(task)
    return auto_check_command(task)


async def check_task(
    task: LiveTask, root: Path, answer: str | None, hidden_env: frozenset[str]
) -> tuple[bool, str]:
    if task.answer_regex:
        matched = re.search(task.answer_regex, (answer or "").strip(), re.S | re.I) is not None
        if matched:
            return True, "answer matched"
        return False, f"answer did not match /{task.answer_regex}/"
    write_task_files(root, task.check_files)
    cmd = task_check_command(task)
    env = {k: v for k, v in os.environ.items() if k not in hidden_env}
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            shell=True,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, "check timed out"
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-300:]


def _token_totals(summary: dict) -> tuple[int, int]:
    by_model = summary["by_model"].values()
    return (
        sum(m["input_tokens"] for m in by_model),
        sum(m["output_tokens"] for m in by_model),
    )


def _secret_values(hide: frozenset[str]) -> list[str]:
    return [v for n in hide if (v := os.environ.get(n))]


async def _run_task(
    config: CoraConfig,
    task: LiveTask,
    spec: ModelSpec,
    protocol: str,
    *,
    max_iterations: int,
    max_task_cost: float,
    state_dir: Path,
    pool: ProviderPool,
    budget: Budget,
    hide: frozenset[str],
    tool_groups: Sequence[str],
    sensor: bool,
    arm: str | None = None,
    run_config: CoraConfig | None = None,
    result_model: str | None = None,
    sensor_source: str = "oracle",
) -> LiveTaskResult:
    budget.begin_task()
    secrets = _secret_values(hide)
    agent: Agent | None = None
    routes: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cora-bench-") as tmp:
        root = Path(tmp)
        try:
            write_task_files(root, task.files)
            if sensor and sensor_source == "auto":
                check = detect_check_command(root)
                use = check is not None
                hook = None
            else:
                use = sensor and task.check is not None
                check = task_check_command(task) if use else None
                hook = (lambda: write_task_files(root, task.check_files)) if use else None
            agent = Agent(
                run_config
                or _run_config(
                    config,
                    spec.id,
                    protocol,
                    max_iterations,
                    max_task_cost,
                    tool_groups,
                    sensor=sensor,
                ),
                root,
                ApprovalPolicy("auto"),
                state_dir=state_dir,
                providers=pool,
                call_gate=budget.gate,
                before_check=hook,
                on_event=lambda e: routes.append(
                    {
                        "tier": e["tier"],
                        "model": e["model"],
                        "grade": e.get("grade"),
                        "reason": e.get("reason"),
                    }
                )
                if e["type"] == "route"
                else None,
            )
            r = await agent.run(
                task.prompt,
                check_command=check,
                sensor=use,
            )
        except Exception as e:
            meter = CostMeter.from_list(
                agent.current.meter if agent is not None and agent.current is not None else []
            )
            budget.settle(meter.total_cost_usd)
            summary = meter.summary()
            input_tokens, output_tokens = _token_totals(summary)
            return LiveTaskResult(
                task=task.id,
                kind=task.kind,
                model=result_model or spec.id,
                protocol=protocol,
                status="error",
                budget_reason=None,
                stop_reason=None,
                iterations=0,
                calls=summary["calls"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=meter.total_cost_usd,
                provider_cost_calls=summary["provider_cost_calls"],
                latency_s=0.0,
                detail=scrub(f"{type(e).__name__}: {e}", secrets)[:300],
                arm=arm,
                difficulty=task.difficulty,
                estimated_minutes=task.estimated_minutes,
                routes=routes,
                **_deleg_fields(summary),
            )
        summary = r.summary
        cost = summary["total_cost_usd"]
        budget.settle(cost)
        budget_reason: str | None = None
        detail = ""
        if r.stop_reason == StopReason.COST_LIMIT:
            status = "stopped_budget"
            budget_reason = budget.tripped or "task"
        elif r.stop_reason != StopReason.FINAL_ANSWER:
            status = "failed"
            detail = f"stop_reason={r.stop_reason.value}"
        else:
            ok, detail = await check_task(task, root, r.answer, hide)
            status = "solved" if ok else "failed"
        input_tokens, output_tokens = _token_totals(summary)
        sg = r.summary.get("sensor", {})
        return LiveTaskResult(
            task=task.id,
            kind=task.kind,
            model=result_model or spec.id,
            protocol=protocol,
            status=status,
            budget_reason=budget_reason,
            stop_reason=r.stop_reason.value,
            iterations=r.session.total_iterations,
            calls=summary["calls"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider_cost_calls=summary["provider_cost_calls"],
            latency_s=0.0,
            detail=scrub(detail, secrets)[:300],
            check_runs=sg.get("checks", 0),
            sensor_retries=sg.get("retries", 0),
            sensor_calls=sg.get("extra_calls", 0),
            sensor_cost_usd=sg.get("extra_cost_usd", 0.0),
            escalated=sg.get("escalated", False),
            arm=arm,
            difficulty=task.difficulty,
            estimated_minutes=task.estimated_minutes,
            routes=routes,
            **_deleg_fields(summary),
        )


class _InterventionCounter:
    def __init__(self) -> None:
        self.count = 0

    def review(self, req: ApprovalRequest) -> str:
        self.count += 1
        return "yes"


async def _run_e2e_task(
    config: CoraConfig,
    task: E2ETask,
    spec: ModelSpec,
    protocol: str,
    *,
    max_iterations: int,
    max_task_cost: float,
    state_dir: Path,
    pool: ProviderPool,
    budget: Budget,
    hide: frozenset[str],
    tool_groups: Sequence[str],
    sensor: bool,
    arm: str | None = None,
    run_config: CoraConfig | None = None,
    result_model: str | None = None,
    approval_mode: str = "policy",
    sensor_source: str = "oracle",
    verify_attempts: int | None = None,
) -> LiveTaskResult:
    auto = sensor and sensor_source == "auto"
    iters, cap = task_limits(task, max_iterations, max_task_cost)
    budget.begin_task(cap)
    secrets = _secret_values(hide)
    routes: list[dict] = []
    counter = _InterventionCounter()
    cfg = run_config or _run_config(
        config,
        spec.id,
        protocol,
        iters,
        cap,
        tool_groups,
        sensor=auto,
        verify_attempts=verify_attempts,
    )
    cfg = dataclasses.replace(
        cfg,
        agent=dataclasses.replace(cfg.agent, max_iterations=iters, max_cost_usd=cap),
    )
    detail = ""
    with tempfile.TemporaryDirectory(prefix="cora-e2e-") as tmp:
        ws = e2e.prepare_workspace(task, Path(tmp))
        check = detect_check_command(ws) if auto else None
        use = check is not None
        gate = PolicyGate(
            PolicySettings(sandbox=cfg.policy.sandbox, source="strict"),
            ws,
            strict=True,
            extra_protected=(task.root,),
            hidden_env=hide,
        )
        agent = Agent(
            cfg,
            ws,
            ApprovalPolicy(approval_mode, review=counter.review),
            state_dir=state_dir,
            providers=pool,
            call_gate=budget.gate,
            policy_gate=gate,
            on_event=lambda e: routes.append(
                {
                    "tier": e["tier"],
                    "model": e["model"],
                    "grade": e.get("grade"),
                    "reason": e.get("reason"),
                }
            )
            if e["type"] == "route"
            else None,
        )
        r = None
        try:
            r = await asyncio.wait_for(
                agent.run(e2e.agent_prompt(task), check_command=check, sensor=use),
                timeout=task.wall_s,
            )
            end_reason = r.stop_reason.value
        except TimeoutError:
            end_reason = "time_limit"
        except Exception as e:
            end_reason = (
                "aborted" if isinstance(e, (BenchAborted, ProviderAccountError)) else "error"
            )
            detail = scrub(f"{type(e).__name__}: {e}", secrets)[:200]
        if r is not None:
            summary = r.summary
            iterations = r.session.total_iterations
        else:
            meter = agent.current.meter if agent.current is not None else []
            summary = CostMeter.from_list(meter).summary()
            iterations = getattr(agent.current, "total_iterations", 0)
        cost = summary["total_cost_usd"]
        budget.settle(cost)
        g = await asyncio.to_thread(e2e.run_grader, task, ws, Path(tmp) / "harness")
        g.output_tail = scrub(g.output_tail, secrets)
        pol = gate.summary(approval_mode)
        if pol is not None:
            for d in pol["decisions"]:
                d["args"] = scrub(d["args"], secrets)
        budget_reason: str | None = None
        if g.full_pass:
            status = "solved"
        elif end_reason == "cost_limit":
            status = "stopped_budget"
            budget_reason = budget.tripped or "task"
        elif end_reason in ("error", "aborted"):
            status = "error"
        else:
            status = "failed"
        detail = (detail + " " if detail else "") + f"end_reason={end_reason} score={g.score:.2f}"
        if g.status != "ok":
            detail += f" grader_error: {g.reason}"
        input_tokens, output_tokens = _token_totals(summary)
        sg = r.summary.get("sensor", {}) if (r is not None and use) else {}
        return LiveTaskResult(
            task=task.id,
            kind=task.kind,
            model=result_model or spec.id,
            protocol=protocol,
            status=status,
            budget_reason=budget_reason,
            stop_reason=r.stop_reason.value if r is not None else None,
            iterations=iterations,
            calls=summary["calls"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider_cost_calls=summary["provider_cost_calls"],
            latency_s=0.0,
            detail=detail[:300],
            check_runs=sg.get("checks", 0),
            sensor_retries=sg.get("retries", 0),
            sensor_calls=sg.get("extra_calls", 0),
            sensor_cost_usd=sg.get("extra_cost_usd", 0.0),
            escalated=sg.get("escalated", False),
            arm=arm,
            difficulty=task.difficulty,
            routes=routes,
            **_deleg_fields(summary),
            score=g.score,
            full_pass=g.full_pass,
            end_reason=end_reason,
            human_interventions=counter.count,
            grader=g.to_dict(),
            policy_denies=pol["deny"] if pol else 0,
            policy_asks=pol["ask"] if pol else 0,
            policy=pol,
        )


def _suite_settings(tasks: Sequence[LiveTask | E2ETask]) -> dict:
    e2e_tasks = [t for t in tasks if isinstance(t, E2ETask)]
    if not e2e_tasks:
        return {"suite": "default"}
    return {
        "suite": "e2e",
        "e2e": {
            "tasks": [
                {
                    "id": t.id,
                    "wall_s": t.wall_s,
                    "cost_usd": t.cost_usd,
                    "max_iterations": t.max_iterations,
                    "grader_timeout_s": t.grader_timeout_s,
                }
                for t in e2e_tasks
            ],
            "grader_timeout_cap_s": e2e.GRADER_TIMEOUT_CAP_S,
            "grader_output_cap_bytes": e2e.MAX_GRADER_OUTPUT_BYTES,
            "policy_profile": "strict",
        },
    }


def _cell_coro(
    task: LiveTask | E2ETask,
    config: CoraConfig,
    spec: ModelSpec,
    protocol: str,
    approval_mode: str,
    **kwargs: Any,
) -> Awaitable[LiveTaskResult]:
    verify = kwargs.pop("verify_attempts", None)
    if isinstance(task, E2ETask):
        return _run_e2e_task(
            config,
            task,
            spec,
            protocol,
            approval_mode=approval_mode,
            verify_attempts=verify,
            **kwargs,
        )
    return _run_task(config, task, spec, protocol, **kwargs)


def _build_report(
    settings: dict,
    results: Sequence[LiveTaskResult],
    budget: Budget,
    tracker: _CallTracker,
    run_started: float,
    clock: Callable[[], float],
    runs_planned: int,
    in_progress: bool,
    extras: Mapping[str, Any] | None,
) -> LiveReport:
    return LiveReport(
        datetime.now(UTC).isoformat(timespec="seconds"),
        settings,
        list(results),
        budget.exhausted,
        aborted=tracker.abort_reason,
        wall_s=max(0.0, clock() - run_started),
        abort_guidance=_abort_guidance(tracker),
        runs_planned=runs_planned,
        in_progress=in_progress,
        extras=dict(extras or {}),
    )


async def run_live_bench(
    config: CoraConfig,
    *,
    models: Sequence[str],
    protocols: Sequence[str],
    tasks: Sequence[LiveTask | E2ETask] = LIVE_TASKS,
    max_cost_usd: float,
    max_task_cost_usd: float,
    max_iterations: int,
    state_dir: Path,
    providers: ProviderPool | None = None,
    on_progress: Callable[[LiveTaskResult, float], None] | None = None,
    tool_groups: Sequence[str] = DEFAULT_BENCH_TOOL_GROUPS,
    sensor: bool = False,
    stall_threshold_s: float = 60.0,
    on_notice: Callable[[str], None] | None = None,
    account: Mapping[str, Any] | None = None,
    clock: Callable[[], float] = bench_clock,
    repeats: int = 1,
    seed: int = DEFAULT_SEED,
    prior: Mapping[str, LiveTaskResult] | None = None,
    on_checkpoint: Callable[[LiveReport], None] | None = None,
    report_extras: Mapping[str, Any] | None = None,
    e2e_approval: str = "policy",
    sensor_source: str = "oracle",
    verify_attempts: int | None = None,
) -> LiveReport:
    if sensor_source not in SENSOR_SOURCES:
        raise ConfigError("--sensor-source must be oracle or auto")
    if repeats < 1:
        raise ConfigError("--repeats must be >= 1")
    validate_verify_attempts(verify_attempts, sensor=sensor, tasks=tasks)
    if verify_attempts is not None and config.agent.ladder:
        raise ConfigError(
            "--verify-attempts needs [agent] ladder = false "
            "(ladder turns the run into the sensor path)"
        )
    specs = validate_live_options(
        config, models, protocols, max_cost_usd, max_task_cost_usd, max_iterations
    )
    groups = normalize_tool_groups(tool_groups)
    pool = providers or ProviderPool(config)
    await _preflight(pool, specs, account, max_cost_usd, on_notice)
    tracker = _CallTracker(clock)
    tracked = _TrackedPool(pool, tracker)
    budget = Budget(max_cost_usd, max_task_cost_usd)
    hide = secret_env_names(config)
    protos = list(dict.fromkeys(protocols))
    planned = repeats * len(tasks) * len(specs) * len(protos)
    results: list[LiveTaskResult] = []
    run_started = clock()
    settings = {
        "max_cost_usd": max_cost_usd,
        "max_task_cost_usd": max_task_cost_usd,
        "max_iterations": max_iterations,
        "stall_threshold_s": float(stall_threshold_s),
        "protocols": protos,
        "tasks": [t.id for t in tasks],
        "tool_groups": list(groups),
        "tools": bench_tool_names(groups),
        "sensor": {
            "enabled": sensor,
            "tripwire": sensor,
            "max_retries": AgentSettings().sensor_max_retries,
            "feedback_chars": AgentSettings().sensor_feedback_chars,
        },
        "models": [_model_meta(s) for s in specs],
        "repeats": repeats,
        "seed": seed,
        **_suite_settings(tasks),
    }
    if verify_attempts is not None:
        settings["verify_attempts"] = verify_attempts
    if sensor and sensor_source == "auto":
        settings["sensor"]["source"] = "auto"
        settings["sensor"]["no_check_tasks"] = [
            t.id for t in tasks if _auto_check(t) is None
        ]

    def checkpoint() -> None:
        if on_checkpoint is not None:
            on_checkpoint(
                _build_report(
                    settings, results, budget, tracker, run_started, clock, planned, True,
                    report_extras,
                )
            )

    for repeat_index in range(repeats):
        for task in tasks:
            for spec in specs:
                for protocol in protos:
                    rid = make_run_id(None, spec.id, protocol, task.id, repeat_index)
                    if prior and rid in prior:
                        results.append(prior[rid])
                        checkpoint()
                        continue
                    if tracker.abort_reason is not None:
                        results.append(
                            dataclasses.replace(
                                _not_run(task, spec.id, protocol),
                                run_id=rid,
                                repeat_index=repeat_index,
                                seed=seed + repeat_index,
                            )
                        )
                        checkpoint()
                        continue
                    if budget.exhausted:
                        result = _skipped(task, spec.id, protocol)
                    else:
                        before = tracker.abort_reason
                        result = await _run_cell(
                            tracker,
                            _cell_coro(
                                task,
                                config,
                                spec,
                                protocol,
                                e2e_approval,
                                max_iterations=max_iterations,
                                max_task_cost=max_task_cost_usd,
                                state_dir=state_dir,
                                pool=tracked,
                                budget=budget,
                                hide=hide,
                                tool_groups=groups,
                                sensor=sensor,
                                sensor_source=sensor_source,
                                verify_attempts=verify_attempts,
                            ),
                        )
                        if (
                            before is None
                            and tracker.abort_reason is not None
                            and result.status == "error"
                        ):
                            result = dataclasses.replace(result, aborted_run=True)
                    result = dataclasses.replace(
                        result,
                        run_id=rid,
                        repeat_index=repeat_index,
                        seed=seed + repeat_index,
                    )
                    results.append(result)
                    if on_progress is not None:
                        on_progress(result, budget.spent_total)
                    checkpoint()
    return _build_report(
        settings, results, budget, tracker, run_started, clock, planned, False, report_extras
    )


async def run_ab_bench(
    config: CoraConfig,
    *,
    arms: Sequence[str],
    model: str,
    protocol: str,
    tasks: Sequence[LiveTask | E2ETask] = MULTI_TASKS,
    max_cost_usd: float,
    max_task_cost_usd: float,
    max_iterations: int,
    state_dir: Path,
    providers: ProviderPool | None = None,
    on_progress: Callable[[LiveTaskResult, float], None] | None = None,
    tool_groups: Sequence[str] = DEFAULT_BENCH_TOOL_GROUPS,
    sensor: bool = False,
    stall_threshold_s: float = 60.0,
    on_notice: Callable[[str], None] | None = None,
    account: Mapping[str, Any] | None = None,
    clock: Callable[[], float] = bench_clock,
    repeats: int = 1,
    seed: int = DEFAULT_SEED,
    prior: Mapping[str, LiveTaskResult] | None = None,
    on_checkpoint: Callable[[LiveReport], None] | None = None,
    report_extras: Mapping[str, Any] | None = None,
    e2e_approval: str = "policy",
    sensor_source: str = "oracle",
    verify_attempts: int | None = None,
) -> LiveReport:
    if sensor_source not in SENSOR_SOURCES:
        raise ConfigError("--sensor-source must be oracle or auto")
    if repeats < 1:
        raise ConfigError("--repeats must be >= 1")
    validate_verify_attempts(verify_attempts, sensor=sensor, tasks=tasks)
    if verify_attempts is not None and config.agent.ladder:
        raise ConfigError(
            "--verify-attempts needs [agent] ladder = false "
            "(ladder turns the run into the sensor path)"
        )
    arms = normalize_arms(arms)
    [cheap] = validate_live_options(
        config, [model], [protocol], max_cost_usd, max_task_cost_usd, max_iterations
    )
    if cheap.tier != "cheap":
        raise ConfigError(f"--ab needs a cheap-tier model; '{model}' is tier {cheap.tier}")
    strong = HeuristicRouter(config).resolve("strong")
    esc = config.escalation
    target = (
        find_model(config.models, esc.strong_model)
        if (esc.enabled and esc.strong_model)
        else strong
    )
    if "strong-only" in arms and (strong is None or not strong.price_known):
        raise ConfigError("--ab strong-only needs a priced strong-tier model in [[models]]")
    if "auto-routed" in arms and (target is None or not target.price_known):
        raise ConfigError(
            "--ab auto-routed needs a priced escalation target "
            "([escalation] strong_model or a strong-tier model in [[models]])"
        )
    groups = normalize_tool_groups(tool_groups)
    pool = providers or ProviderPool(config)
    used_models = [cheap]
    extra = []
    if "strong-only" in arms and strong is not None:
        extra.append(strong)
    if "auto-routed" in arms and target is not None:
        extra.append(target)
    for spec in extra:
        if all(s.id != spec.id for s in used_models):
            used_models.append(spec)
    await _preflight(pool, used_models, account, max_cost_usd, on_notice)
    tracker = _CallTracker(clock)
    tracked = _TrackedPool(pool, tracker)
    budget = Budget(max_cost_usd, max_task_cost_usd)
    hide = secret_env_names(config)
    planned = repeats * len(tasks) * len(arms)
    results: list[LiveTaskResult] = []
    run_started = clock()
    settings = {
        "max_cost_usd": max_cost_usd,
        "max_task_cost_usd": max_task_cost_usd,
        "max_iterations": max_iterations,
        "stall_threshold_s": float(stall_threshold_s),
        "protocols": [protocol],
        "tasks": [t.id for t in tasks],
        "tool_groups": list(groups),
        "tools": bench_tool_names(groups),
        "sensor": {
            "enabled": sensor,
            "tripwire": sensor,
            "max_retries": AgentSettings().sensor_max_retries,
            "feedback_chars": AgentSettings().sensor_feedback_chars,
        },
        "models": [_model_meta(s) for s in used_models],
        "ab": {
            "arms": list(arms),
            "model": cheap.id,
            "strong_model": strong.id
            if (strong is not None and any(a in ("strong-only", "auto-routed") for a in arms))
            else None,
            "escalation_target": target.id if "auto-routed" in arms else None,
            "protocol": protocol,
            "delegation_tool_groups": list(normalize_tool_groups([*groups, "delegate"])),
            "delegation": {
                "explore_concurrency": config.delegation.explore_concurrency,
                "explore_max_calls": config.delegation.explore_max_calls,
                "max_steps": config.delegation.max_steps,
                "max_tokens": config.delegation.max_tokens,
                "summary_max_chars": config.delegation.summary_max_chars,
            },
            "difficulty_thresholds_min": list(DIFFICULTY_THRESHOLDS),
        },
        "repeats": repeats,
        "seed": seed,
        **_suite_settings(tasks),
    }
    if verify_attempts is not None:
        settings["verify_attempts"] = verify_attempts
    if sensor and sensor_source == "auto":
        settings["sensor"]["source"] = "auto"
        settings["sensor"]["no_check_tasks"] = [
            t.id for t in tasks if _auto_check(t) is None
        ]

    def checkpoint() -> None:
        if on_checkpoint is not None:
            on_checkpoint(
                _build_report(
                    settings, results, budget, tracker, run_started, clock, planned, True,
                    report_extras,
                )
            )

    for repeat_index in range(repeats):
        for task in tasks:
            for arm in arms:
                if arm == "auto-routed":
                    model_id = "auto"
                elif arm == "strong-only" and strong is not None:
                    model_id = strong.id
                else:
                    model_id = cheap.id
                rid = make_run_id(arm, model_id, protocol, task.id, repeat_index)
                if prior and rid in prior:
                    results.append(prior[rid])
                    checkpoint()
                    continue
                if tracker.abort_reason is not None:
                    results.append(
                        dataclasses.replace(
                            _not_run(task, model_id, protocol, arm),
                            run_id=rid,
                            repeat_index=repeat_index,
                            seed=seed + repeat_index,
                        )
                    )
                    checkpoint()
                    continue
                if budget.exhausted:
                    result = _skipped(task, model_id, protocol, arm)
                else:
                    before = tracker.abort_reason
                    result = await _run_cell(
                        tracker,
                        _cell_coro(
                            task,
                            config,
                            cheap,
                            protocol,
                            e2e_approval,
                            max_iterations=max_iterations,
                            max_task_cost=max_task_cost_usd,
                            state_dir=state_dir,
                            pool=tracked,
                            budget=budget,
                            hide=hide,
                            tool_groups=groups,
                            sensor=sensor,
                            sensor_source=sensor_source,
                            arm=arm,
                            run_config=_arm_config(
                                config,
                                arm,
                                cheap,
                                strong,
                                protocol,
                                max_iterations,
                                max_task_cost_usd,
                                groups,
                                sensor,
                                verify_attempts=verify_attempts,
                            ),
                            result_model=model_id,
                        ),
                    )
                    if (
                        before is None
                        and tracker.abort_reason is not None
                        and result.status == "error"
                    ):
                        result = dataclasses.replace(result, aborted_run=True)
                result = dataclasses.replace(
                    result,
                    run_id=rid,
                    repeat_index=repeat_index,
                    seed=seed + repeat_index,
                )
                results.append(result)
                if on_progress is not None:
                    on_progress(result, budget.spent_total)
                checkpoint()
    return _build_report(
        settings, results, budget, tracker, run_started, clock, planned, False, report_extras
    )
