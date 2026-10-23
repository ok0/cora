from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import Any

from cora.core import finalgate
from cora.core.budget import BudgetGovernor, BudgetLimits, BudgetUsage, projected_call_cost
from cora.core.checks import (
    SELFTEST_COMMAND,
    SELFTEST_DIR,
    detect_check_command,
    is_python_workspace,
    snapshot_tests,
    tampered_tests,
)
from cora.core.config import (
    GATE_KEYS,
    TIERS,
    CoraConfig,
    ModelSpec,
    effective_protocol,
    find_model,
    model_ref,
    secret_env_names,
)
from cora.core.decider import Decider, DecisionHooks, DecisionRecord, accepted, group_question
from cora.core.deciders import apply_tier_choice, make_decider
from cora.core.delegation import (
    DO_IT_YOURSELF,
    DelegateTool,
    SubagentBudgetExceeded,
    clip_summary,
    explore_registry,
    run_subagent,
)
from cora.core.errors import ConfigError, InvalidTransition
from cora.core.escalation import EscalationPolicy, EscalationSignals
from cora.core.memory import (
    PROTECTED_MARK,
    SUMMARY_MAX_TOKENS,
    PersistentStore,
    WorkingMemory,
    mask_command,
    mask_path,
    read_path_of,
    scrub_secrets,
    summary_messages,
)
from cora.core.metering import CostMeter, DelegationStats, projected_cost
from cora.core.native import NATIVE_EMPTY_REPLY, decode_arguments, flatten_tool_messages
from cora.core.observability import EventLog
from cora.core.policy import WRITE_TOOLS, PolicyGate, approval_mode_of, load_policy
from cora.core.prompts import (
    ESCALATION_NOTE,
    EXPLORE_NOTE,
    SELFTEST_FEEDBACK,
    SENSOR_FEEDBACK,
    SUBAGENT_NOTE,
    TESTS_MODIFIED,
    TRIPWIRE_NOTE,
    TRIPWIRE_STOP,
    build_system_prompt,
    repeat_feedback,
)
from cora.core.providers import ProviderPool, provider_events, provider_workspace
from cora.core.providers.base import ProviderTimeout, call_with_timeout
from cora.core.react import (
    FINAL_MARKER,
    INPUT_ERROR,
    MAX_ACTIONS_PER_TURN,
    FinalAnswerFilter,
    first_required_arg,
    has_delegate_action_line,
    located_input_error,
    parse_turn,
    truncated_error,
)
from cora.core.reflexion import reflect
from cora.core.repeat import REPEAT_TEMPERATURE, RepeatTracker
from cora.core.repomap import CACHE_RELPATH, RepoMap
from cora.core.router import HeuristicRouter, RouteDecision, prompt_features
from cora.core.shellguard import PathGuard, default_protected
from cora.core.state import AgentState, Session, SessionStore, StopReason, new_session_id
from cora.core.toolgroups import (
    OPTIONAL_GROUPS,
    auto_hidden_groups,
    auto_rule_active,
    excluded_tools,
    group_of,
    request_signals,
)
from cora.core.tools import (
    ApprovalPolicy,
    SubmitPlanTool,
    Tool,
    ToolContext,
    ToolRegistry,
    ToolResult,
    Workspace,
    default_tools,
)
from cora.core.tools.builtin import OLD_NOT_FOUND_PREFIX, RunShellTool
from cora.core.tools.mcp import McpManager
from cora.core.tripwire import Tripwire, normalize_error
from cora.core.types import (
    CompletionRequest,
    CompletionResponse,
    Message,
    estimate_tokens,
    messages_tokens,
)

REFLECT_MAX_TOKENS = 400
STOP_SEQS = ["\nObservation:"]
FILE_OPS = {"edit_file": "edit", "write_file": "write", "delete_file": "delete"}
STOP_FOR_CAP = {
    "cost": StopReason.COST_LIMIT,
    "iterations": StopReason.MAX_ITERATIONS,
    "wall": StopReason.BUDGET_EXCEEDED,
    "tool_calls": StopReason.BUDGET_EXCEEDED,
}


@dataclass
class RunResult:
    session: Session
    answer: str | None
    stop_reason: StopReason
    summary: dict
    log_path: Path


def _target(args: object) -> str:
    if isinstance(args, dict):
        for key in ("path", "command", "pattern", "url"):
            if key in args:
                return str(args[key]).replace("\n", " ")[:120]
    return ""


def _log_tool(
    log: EventLog,
    name: str,
    args: Any,
    res: ToolResult,
    *,
    hook: Callable[[str], None] | None = None,
    **extra: Any,
) -> None:
    if hook is not None:
        hook(res.output)
    log.emit(
        "tool_call",
        tool=name,
        args=json.dumps(args, ensure_ascii=False)[:500],
        target=_target(args),
        ok=res.ok,
        output_chars=len(res.output),
        output_lines=(res.output.count("\n") + 1) if res.output else 0,
        output_head=res.output[:300],
        **extra,
    )


def _multi_observation(
    names: Sequence[str], results: Sequence[ToolResult], limit: int, dropped: int
) -> str:
    per = max(200, limit // len(names) - 64)
    parts = []
    for i, (name, r) in enumerate(zip(names, results, strict=True), 1):
        out = r.output if len(r.output) <= per else r.output[:per] + "\n...[truncated]"
        parts.append(f"Observation {i} ({name}): {out}")
    if dropped:
        parts.append(
            f"Note: only the first {len(names)} actions were run; {dropped} more were ignored."
        )
    return "\n\n".join(parts)


async def _delegation_unavailable(task: str, mode: str = "general") -> ToolResult:
    return ToolResult(False, "delegation is unavailable")


class Agent:
    def __init__(
        self,
        config: CoraConfig,
        workspace: Path,
        approval: ApprovalPolicy,
        *,
        state_dir: Path | None = None,
        tools: Sequence[Tool] | None = None,
        providers: ProviderPool | None = None,
        on_event: Callable[[dict], None] | None = None,
        on_answer_delta: Callable[[str], None] | None = None,
        on_tool_output: Callable[[str], None] | None = None,
        project_context: str = "",
        call_gate: Callable[[float, float], bool] | None = None,
        before_check: Callable[[], None] | None = None,
        decider: Decider | None = None,
        mcp: McpManager | None = None,
        policy_gate: PolicyGate | None = None,
        governor: BudgetGovernor | None = None,
    ) -> None:
        self.config = config
        self.workspace = workspace
        self.state_dir = state_dir if state_dir is not None else workspace / ".cora"
        self.on_event = on_event
        self.on_answer_delta = on_answer_delta
        self.on_tool_output = on_tool_output
        self.project_context = project_context
        self.call_gate = call_gate
        self.before_check = before_check
        self.current: Session | None = None
        self.clock: Callable[[], float] = time.monotonic
        self.providers = providers or ProviderPool(config)
        self.decider: Decider = (
            decider if decider is not None else make_decider(config, self.providers)
        )
        self.mcp = mcp
        self.router = HeuristicRouter(config)
        self.tools = ToolRegistry(tools or default_tools())
        gate = policy_gate or PolicyGate(
            load_policy(config.policy, Path(workspace)),
            Path(workspace),
            hidden_env=secret_env_names(config),
        )
        self.governor = (
            governor
            if governor is not None
            else BudgetGovernor(
                BudgetLimits.from_agent(config.agent),
                warn_fraction=config.agent.budget_warn_fraction,
                project_cost=False,
            )
        )
        self._stop_requested = False
        self.ctx = ToolContext(
            Workspace(workspace),
            approval,
            config.agent.shell_timeout_s,
            hidden_env=secret_env_names(config),
            limits=config.tools,
            disabled_groups=frozenset(config.tool_groups.disabled),
            gate=gate,
            budget=self.governor,
            located_errors=config.agent.located_errors,
            raw_file_body=config.agent.raw_file_body,
        )
        self.policy_warnings: list[str] = list(gate.warnings)
        self._has_attachments = False
        self.sessions = SessionStore(self.state_dir / "sessions")
        self.store = PersistentStore(self.state_dir / "memory")

    def request_stop(self) -> None:
        self._stop_requested = True

    def registry_for(
        self, delegate_runner: Callable[[str, str], Awaitable[ToolResult]] | None = None
    ) -> ToolRegistry:
        reg = self.tools
        if self.config.delegation.enabled:
            reg = reg.extended(
                [
                    DelegateTool(
                        delegate_runner or _delegation_unavailable,
                        parallel_explore=self.config.delegation.parallel_explore,
                    )
                ]
            )
        if self.ctx.plan_mode:
            reg = reg.extended([SubmitPlanTool()])
        return reg

    async def _with_mcp(self, reg: ToolRegistry) -> ToolRegistry:
        if self.mcp is None:
            return reg
        servers = self.mcp.active_servers(self.ctx.disabled_groups)
        if not servers:
            return reg
        tools = await asyncio.to_thread(self.mcp.ensure_tools, servers)
        taken = set(reg.names())
        return reg.extended([t for t in tools if t.name not in taken])

    def _compress_chars(self) -> int:
        c = self.config.cache
        return c.compress_chars if c.compress_observations else 0

    def _new_memory(self, session_id: str) -> WorkingMemory:
        return WorkingMemory(
            self.config.memory,
            self.store,
            session_id,
            dedupe_reads=self.config.context.dedupe_reads,
            compress_chars=self._compress_chars(),
        )

    def _repo_map(self, log: EventLog) -> str:
        c = self.config.context
        if not c.repo_map:
            return ""
        root = self.ctx.workspace.root
        rm = RepoMap.build(root, PathGuard(root, default_protected()),
                           max_files=c.max_files, cache_path=self.state_dir / CACHE_RELPATH)
        text = rm.render(c.repo_map_max_chars)
        log.emit("repo_map", files=len(rm.entries), parsed=rm.parsed, capped=rm.capped,
                 chars=len(text))
        return text

    def _spec(self, model_id: str | None, tier: str | None) -> ModelSpec:
        spec = find_model(self.config.models, model_id)
        if spec is None:
            spec = next((m for m in self.config.models if m.tier == tier), None)
        if spec is None:
            raise ConfigError(f"model '{model_id}' is not in the current model configuration")
        return spec

    async def run(
        self,
        task: str,
        *,
        check_command: str | None = None,
        session: Session | None = None,
        attachments: str = "",
        sensor: bool = False,
    ) -> RunResult:
        self._has_attachments = bool(attachments.strip())
        root = self.ctx.workspace.root
        cfg = self.config.agent
        source = "explicit" if check_command is not None else None
        if check_command is None and cfg.auto_check:
            check_command = detect_check_command(root)
            source = "auto" if check_command is not None else None
        has_check = check_command is not None
        use_sensor = (sensor or cfg.ladder) and has_check
        selftest = cfg.selftest and not has_check and is_python_workspace(root)
        hashes = snapshot_tests(root) if cfg.tamper_guard and has_check else {}
        if session is None:
            s = Session(
                id=new_session_id(),
                task=task,
                check_command=check_command,
                sensor=use_sensor,
                check_source=source,
                test_hashes=hashes,
                selftest=selftest,
            )
            memory = self._new_memory(s.id)
            memory.pin(Message("user", f"Task: {task}{attachments}"))
            s.transition(AgentState.ROUTING)
        else:
            s = session
            s.task = task
            s.check_command = check_command
            s.sensor = use_sensor
            s.check_source = source
            s.test_hashes = hashes
            s.selftest = selftest
            s.selftest_result = None
            s.ladder_reflected = False
            s.ladder_exhausted = False
            s.check_runs = 0
            s.sensor_retries = 0
            s.sensor_calls = 0
            s.sensor_cost_usd = 0.0
            s.escalated = False
            s.escalation_trigger = None
            s.escalated_at_check = 0
            s.iteration = 0
            s.attempt = 0
            s.stop_reason = None
            s.final_answer = None
            memory = WorkingMemory.from_dict(
                s.memory, self.config.memory, self.store, s.id,
                dedupe_reads=self.config.context.dedupe_reads,
                compress_chars=self._compress_chars(),
            )
            memory.pin(Message("user", f"New request: {task}{attachments}"))
            try:
                s.transition(AgentState.ROUTING)
            except InvalidTransition:
                s.force_state(AgentState.ROUTING)
        self.current = s
        return await self._execute(s, memory)

    async def resume(self, session_id: str) -> RunResult:
        s = self.sessions.load(session_id)
        self.current = s
        memory = WorkingMemory.from_dict(
            s.memory, self.config.memory, self.store, s.id,
            dedupe_reads=self.config.context.dedupe_reads,
            compress_chars=self._compress_chars(),
        )
        log_path = self.sessions.dir_for(s.id) / "events.jsonl"
        if s.state == AgentState.DONE:
            return RunResult(
                s,
                s.final_answer,
                StopReason(s.stop_reason or StopReason.FINAL_ANSWER.value),
                CostMeter.from_list(s.meter).summary(s.delegation_stats),
                log_path,
            )
        if s.state in {
            AgentState.THINKING,
            AgentState.ACTING,
            AgentState.OBSERVING,
            AgentState.STOPPED,
            AgentState.FAILED,
        }:
            s.force_state(AgentState.THINKING)
        elif s.state == AgentState.IDLE:
            s.force_state(AgentState.ROUTING)
        log = EventLog(log_path, self.on_event)
        log.emit("resumed", state=s.state.value, iteration=s.iteration)
        self._has_attachments = False
        self.ctx.hidden_groups = set()
        return await self._execute(s, memory)

    async def _execute(self, session: Session, memory: WorkingMemory) -> RunResult:
        log = EventLog(self.sessions.dir_for(session.id) / "events.jsonl", self.on_event)
        meter = CostMeter.from_list(session.meter)
        base_stats = DelegationStats.from_dict(session.delegation_stats)
        req_stats = DelegationStats()

        def delegate_on() -> bool:
            return "delegate" in run_tools.names()

        def count_attempts(names: Iterable[str]) -> None:
            if delegate_on():
                req_stats.attempts += sum(1 for n in names if n == "delegate")

        def count_unparsed(text: str) -> None:
            if delegate_on() and has_delegate_action_line(text):
                req_stats.attempts += 1
                req_stats.attempts_unparsed += 1

        gov = self.governor
        prior = (session.budget or {}).get("used") or {}
        gov.begin(
            BudgetUsage(
                cost_usd=meter.total_cost_usd,
                iterations=session.iteration,
                wall_s=float(prior.get("wall_s", 0.0)),
                tool_calls=int(prior.get("tool_calls", 0)),
            )
        )
        counted = [meter.total_cost_usd]

        def sync_budget() -> None:
            delta = meter.total_cost_usd - counted[0]
            if delta > 0:
                gov.add_cost(delta)
                counted[0] += delta
            for cap, used, limit in gov.drain_warnings():
                log.emit("budget_warning", cap=cap, used=used, limit=limit,
                         fraction=gov.warn_fraction)

        def check_model(projected: float = 0.0, *, iterations: bool = True) -> str | None:
            sync_budget()
            cap = gov.check_model_call(projected, iterations=iterations)
            sync_budget()
            return cap

        react_cap = self.config.agent.react_max_tokens
        gate_keys = {k for k in GATE_KEYS if getattr(self.config.agent, k)}
        tracker = finalgate.EditTracker()
        gate_fired: set[str] = set()
        stub_base = (
            finalgate.defs_snapshot(self.ctx.workspace.root) if "stub_check" in gate_keys else {}
        )
        oguard = (
            finalgate.OverwriteGuard.snapshot(self.ctx.workspace.root)
            if self.config.agent.overwrite_guard
            else None
        )

        def projected_for(
            msgs: list[Message], spec: ModelSpec, tools: list[dict] | None,
            max_tokens: int = react_cap,
        ) -> float:
            tokens = messages_tokens(msgs) + (estimate_tokens(json.dumps(tools)) if tools else 0)
            return projected_call_cost(spec, tokens, max_tokens)

        def decider_gate(spent: float, projected: float) -> bool:
            if self.call_gate is not None and not self.call_gate(spent, projected):
                return False
            return check_model(projected if gov.project_cost else 0.0, iterations=False) is None

        trip_on = session.sensor or self.config.agent.tripwire
        trip = Tripwire()
        esc = self.config.escalation
        policy = EscalationPolicy(esc)
        cheap_first = self.config.router.mode == "cheap_first"
        stuck = [0]
        progress = [False]
        seen_iter = [session.iteration]
        seen_reads: set[str] = set()
        passed = [False]
        run_tools = self.tools
        decisions: list[DecisionRecord] = []
        step_failures: list[str] = []
        rep = RepeatTracker() if self.config.agent.repeat_breaker else None
        boost = [False]

        def repeat_note(text: str, failure: tuple[str, str | None] | None) -> str | None:
            if rep is None:
                return None
            sig = rep.observe(text, failure)
            if sig is None:
                return None
            log.emit("repeat_detected", iteration=session.iteration, kind=sig.kind, count=sig.count)
            if sig.boost:
                boost[0] = True
            if not sig.feedback:
                return None
            return repeat_feedback(sig.kind, self.config.agent.raw_file_body)

        def edit_mismatch(calls, results) -> tuple[str, str | None] | None:
            for c, r in zip(calls, results, strict=True):
                if c.name == "edit_file" and not r.ok and r.output.startswith(OLD_NOT_FOUND_PREFIX):
                    path = c.args.get("path") if isinstance(c.args, dict) else None
                    return ("edit_mismatch", path)
            return None

        def with_note(obs: str, note: str | None) -> str:
            return f"{obs}\n{note}" if note else obs

        gate = self.ctx.gate
        if gate is not None:
            gate.begin_run()
            gate.guard.selftest_writable = session.selftest
            gate.sink = lambda rec: log.emit("policy_decision", **rec)
            for w in gate.warnings:
                log.emit("policy_warning", message=w)

        def on_decision(rec: DecisionRecord) -> None:
            decisions.append(rec)
            log.emit("decision", **rec.to_event())

        self.decider.begin_request(
            DecisionHooks(meter=meter, call_gate=decider_gate, on_record=on_decision)
        )

        repo_map = self._repo_map(log)
        terse = self.config.cache.tool_descriptions == "terse"

        def system_prompt(protocol: str = "react") -> str:
            ex = excluded()
            return build_system_prompt(
                self.ctx.workspace.root,
                run_tools.describe(
                    ex,
                    terse=terse,
                    raw_blocks=self.config.agent.raw_file_body and protocol == "react",
                ),
                session.reflections,
                self.project_context,
                parallel=self.config.agent.max_parallel_tools > 1,
                protocol=protocol,
                plan_mode=self.ctx.plan_mode,
                repo_map=repo_map,
                selftest=session.selftest,
                nudge=self.config.delegation.nudge
                and "delegate" in run_tools.names()
                and "delegate" not in ex,
            )

        log.emit(
            "models",
            models=[
                {
                    "tier": m.tier,
                    "id": m.id,
                    "provider": m.provider,
                    "source": m.source,
                    "price_known": m.price_known,
                }
                for m in self.config.models
            ],
        )
        if (
            session.check_source == "auto"
            and session.state == AgentState.ROUTING
            and session.attempt == 0
        ):
            log.emit("check_detected", command=session.check_command)

        def save() -> None:
            session.memory = memory.to_dict()
            session.meter = meter.to_list()
            session.delegation_stats = base_stats.merged(req_stats).to_dict()
            sync_budget()
            session.budget = gov.to_dict()
            self.sessions.save(session)

        def sync_groups() -> None:
            shown = {
                g
                for g in OPTIONAL_GROUPS
                if g not in self.ctx.hidden_groups and g not in self.ctx.disabled_groups
            }
            if not shown <= set(session.tool_groups):
                session.tool_groups = sorted(set(session.tool_groups) | shown)

        def excluded() -> frozenset[str]:
            sync_groups()
            return excluded_tools(
                run_tools.names(), self.ctx.disabled_groups | self.ctx.hidden_groups
            )

        def wall_left() -> float | None:
            lim = gov.limits.wall_s
            return None if lim is None else max(0.0, lim - gov.usage().wall_s)

        async def call_model(
            messages: list[Message],
            spec: ModelSpec,
            tier: str,
            purpose: str,
            max_tokens: int,
            tools: list[dict] | None = None,
            temperature: float = 0.0,
        ) -> CompletionResponse:
            provider = self.providers.get(spec.provider)

            def sink(kind: str, data: dict) -> None:
                log.emit(kind, model=spec.id, provider=spec.provider, purpose=purpose, **data)

            req = CompletionRequest(
                spec.id,
                list(messages) if tools else flatten_tool_messages(messages),
                max_tokens,
                temperature,
                STOP_SEQS if purpose in ("react", "delegate") and tools is None else None,
                tools,
                cache_prefix=self.config.cache.prompt_cache and spec.cache,
            )
            t0 = self.clock()
            stream_fn = getattr(provider, "stream", None)

            async def once() -> CompletionResponse:
                streaming = (
                    purpose == "react"
                    and self.on_answer_delta is not None
                    and stream_fn is not None
                )
                if streaming:
                    if tools is None:
                        filt = FinalAnswerFilter()
                        on_delta = self.on_answer_delta

                        def on_text(chunk: str) -> None:
                            out = filt.feed(chunk)
                            if out:
                                on_delta(out)

                        return await stream_fn(req, on_text)
                    return await stream_fn(req, self.on_answer_delta)
                return await provider.complete(req)

            with provider_events(sink), provider_workspace(self.workspace):
                resp = await call_with_timeout(
                    once,
                    model=spec.id,
                    timeout_s=self.config.agent.call_timeout_s,
                    budget_s=wall_left(),
                )
            latency = self.clock() - t0
            rec = meter.record(
                spec,
                tier,
                purpose,
                resp.input_tokens,
                resp.output_tokens,
                cost_usd=resp.cost_usd,
                cached_input_tokens=resp.cached_input_tokens,
                latency_s=latency,
                replayed=resp.replayed,
            )
            if session.sensor_retries > 0:
                session.sensor_calls += 1
                session.sensor_cost_usd += rec.cost_usd
            log.emit(
                "llm_call",
                model=spec.id,
                provider=spec.provider,
                latency_s=rec.latency_s,
                tier=tier,
                purpose=purpose,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=rec.cost_usd if rec.price_known else None,
                price_known=rec.price_known,
                prompt_tokens_estimate=messages_tokens(messages),
                protocol="native" if tools else "react",
                tool_calls=len(resp.tool_calls),
                cost_source=rec.cost_source,
                **(
                    {"cached_input_tokens": resp.cached_input_tokens}
                    if resp.cached_input_tokens
                    else {}
                ),
            )
            return resp

        async def call_llm(
            messages: list[Message],
            spec: ModelSpec,
            tier: str,
            purpose: str,
            max_tokens: int,
        ) -> str:
            return (await call_model(messages, spec, tier, purpose, max_tokens)).text

        def gate_ok(msgs: list[Message], spec: ModelSpec, tools: list[dict] | None) -> bool:
            if self.call_gate is None:
                return True
            tokens = messages_tokens(msgs) + (estimate_tokens(json.dumps(tools)) if tools else 0)
            projected = projected_cost(spec, tokens, react_cap)
            if self.call_gate(meter.total_cost_usd, projected):
                return True
            log.emit("budget_gate", spent_usd=meter.total_cost_usd, projected_usd=projected)
            return False

        def result_summary() -> dict:
            s = meter.summary(base_stats.merged(req_stats).to_dict())
            if req_stats.invocations or req_stats.refused or req_stats.attempts:
                log.emit("delegation_summary", scope="request", **req_stats.to_dict())
            if trip_on:
                s["sensor"] = {
                    "enabled": session.sensor,
                    "checks": session.check_runs,
                    "retries": session.sensor_retries,
                    "extra_calls": session.sensor_calls,
                    "extra_cost_usd": session.sensor_cost_usd,
                    "escalated": session.escalated,
                }
                if self.config.agent.ladder:
                    s["sensor"]["ladder_exhausted"] = session.ladder_exhausted
            if esc.enabled:
                s["escalation"] = {"trigger": session.escalation_trigger,
                                   "escalated": session.escalated, "model": session.model_id}
            if session.selftest_result is not None:
                s["selftest"] = dict(session.selftest_result)
            if decisions:
                s["decider"] = {
                    "decisions": len(decisions),
                    "fallbacks": sum(1 for d in decisions if d.fallback_used),
                    "cost_usd": sum(d.cost_usd for d in decisions),
                }
            pol = gate.summary(approval_mode_of(self.ctx.approval)) if gate is not None else None
            if pol is not None:
                s["policy"] = pol
                log.emit("policy_summary", mode=pol["mode"], source=pol["source"],
                         allow=pol["allow"], ask=pol["ask"], deny=pol["deny"],
                         ask_resolved_deny=pol["ask_resolved_deny"])
            return s

        def stop(reason: StopReason) -> RunResult:
            session.transition(AgentState.STOPPED)
            session.stop_reason = reason.value
            log.emit("stop", reason=reason.value)
            save()
            return RunResult(session, None, reason, result_summary(), log.path)

        def budget_stop(cap: str) -> RunResult:
            d = gov.to_dict()
            log.emit("budget_trip", cap=cap, used=d["used"], limits=d["limits"])
            return stop(STOP_FOR_CAP[cap])

        def finish() -> RunResult:
            session.transition(AgentState.DONE)
            session.stop_reason = StopReason.FINAL_ANSWER.value
            log.emit("stop", reason=StopReason.FINAL_ANSWER.value)
            save()
            return RunResult(
                session,
                session.final_answer,
                StopReason.FINAL_ANSWER,
                result_summary(),
                log.path,
            )

        def reset_stuck() -> None:
            stuck[0] = 0
            progress[0] = False
            seen_iter[0] = session.iteration

        def note_tool(name: str, args: Any, ok: bool) -> None:
            tracker.note(name, args, ok)
            if ok and name in WRITE_TOOLS:
                progress[0] = True
            p = read_path_of(self.ctx.workspace.root, name, args, ok)
            if p is not None and p not in seen_reads:
                seen_reads.add(p)
                progress[0] = True
            if oguard is not None:
                oguard.note(name, args, ok)

        def edit_note() -> str | None:
            paths = tracker.drain()
            if "compile_check" not in gate_keys:
                return None
            errs = finalgate.syntax_errors(self.ctx.workspace.root, paths)
            if not errs:
                return None
            log.emit("gate_feedback", mechanism="compile_check", stage="edit", items=errs[:20])
            ledger_decision("gate", "compile_check (edit)")
            return finalgate.SYNTAX_EDIT_NOTE.format(lines=finalgate.format_lines(errs))

        ledger_seen = [""]

        def lguard() -> PathGuard | None:
            return getattr(self.ctx.gate, "guard", None)

        def ltext(s: str) -> str:
            return scrub_secrets(s, os.environ, self.ctx.hidden_env)

        def ledger_decision(kind: str, text: str) -> None:
            if memory.ledger is not None:
                memory.ledger.note_decision(kind, ltext(text), session.iteration)

        def ledger_check(command: str, ok: bool, output: str) -> None:
            if memory.ledger is not None:
                memory.ledger.note_check(
                    ltext(mask_command(lguard(), command)), ok, session.iteration, ltext(output)
                )

        def ledger_tool(name: str, args: Any, r: ToolResult) -> None:
            if memory.ledger is None or not isinstance(args, dict):
                return
            if name in FILE_OPS and r.ok:
                p = mask_path(self.ctx.workspace.root, lguard(), args.get("path"))
                if p is not None:
                    memory.ledger.note_file(p, FILE_OPS[name], session.iteration)
            elif name == "run_shell" and isinstance(args.get("command"), str) \
                    and finalgate.is_check_command(args["command"]):
                ledger_check(args["command"], r.ok, r.output)

        async def summarize(ev: list[tuple[Message, str | None]]) -> None:
            spec_c = self._spec(None, "cheap")
            if check_model(iterations=False) is not None or not gate_ok([], spec_c, None):
                log.emit("summary_call", ok=False, evicted=len(ev), error="budget")
                return
            try:
                text = await call_llm(
                    summary_messages(ev), spec_c, spec_c.tier, "summary", SUMMARY_MAX_TOKENS
                )
            except Exception as e:
                log.emit("summary_call", ok=False, evicted=len(ev), error=type(e).__name__)
                return
            added = memory.ledger.add_summary(ltext(text))
            log.emit("summary_call", ok=True, evicted=len(ev), chars=len(added))

        async def after_build() -> None:
            led = memory.ledger
            if led is None:
                return
            ev = memory.drain_evicted()
            if ev:
                log.emit(
                    "ledger_evict_note",
                    evicted=len(ev),
                    read_paths=[t for _, t in ev if t],
                    iteration=session.iteration,
                )
                if self.config.memory.summarize == "llm":
                    await summarize(ev)
            if memory.ledger_text != ledger_seen[0]:
                ledger_seen[0] = memory.ledger_text
                log.emit(
                    "ledger_update",
                    chars=len(memory.ledger_text),
                    files=len(led.files),
                    checks=len(led.checks),
                    decisions=len(led.decisions),
                    read_evicted=len(led.read_evicted),
                    summaries=len(led.summaries),
                    iteration=session.iteration,
                )

        def guard_refusal(name: str, args: Any) -> ToolResult | None:
            if oguard is None:
                return None
            hit = oguard.check(name, args)
            if hit is None:
                return None
            log.emit(
                "overwrite_refused",
                mechanism="overwrite_guard",
                path=hit[0],
                iteration=session.iteration,
            )
            ledger_decision(
                "overwrite_refused",
                mask_path(self.ctx.workspace.root, lguard(), hit[0]) or PROTECTED_MARK,
            )
            return ToolResult(False, hit[1])

        async def exec_one(name: str, args: Any) -> ToolResult:
            count_attempts((name,))
            refused = guard_refusal(name, args)
            return refused if refused is not None else await run_tools.execute(name, args, self.ctx)

        async def exec_many(calls: list[tuple[str, Any]]) -> list[ToolResult]:
            count_attempts(n for n, _ in calls)
            refused = [guard_refusal(n, a) for n, a in calls]
            live = [i for i, r in enumerate(refused) if r is None]
            if len(live) == len(calls):
                return await run_tools.execute_many(
                    calls, self.ctx, self.config.agent.max_parallel_tools
                )
            ran = (
                await run_tools.execute_many(
                    [calls[i] for i in live], self.ctx, self.config.agent.max_parallel_tools
                )
                if live
                else []
            )
            merged = list(refused)
            for i, r in zip(live, ran, strict=True):
                merged[i] = r
            return [r for r in merged if r is not None]

        def final_gate() -> str | None:
            if not gate_keys or self.ctx.plan_mode:
                return None
            lim = gov.limits.iterations
            if lim is not None and gov.usage().iterations >= lim:
                return None
            root = self.ctx.workspace.root
            found: list[tuple[str, str, dict]] = []
            if "compile_check" in gate_keys and "compile_check" not in gate_fired:
                errs = finalgate.syntax_errors(root, tracker.edited)
                if errs:
                    found.append((
                        "compile_check",
                        finalgate.SYNTAX_FEEDBACK.format(lines=finalgate.format_lines(errs)),
                        {"items": errs[:20]},
                    ))
            if "stub_check" in gate_keys and "stub_check" not in gate_fired and tracker.edited:
                items = finalgate.stub_findings(root, stub_base, tracker.edited)
                if items:
                    found.append((
                        "stub_check",
                        finalgate.STUB_FEEDBACK.format(lines=finalgate.format_lines(items)),
                        {"items": items[:20]},
                    ))
            if (
                "verify_before_final" in gate_keys
                and "verify_before_final" not in gate_fired
                and session.check_command is None
                and tracker.unchecked
            ):
                found.append(("verify_before_final", finalgate.VERIFY_FEEDBACK, {}))
            if (
                "edge_case_prompt" in gate_keys
                and "edge_case_prompt" not in gate_fired
                and tracker.edited
            ):
                found.append(("edge_case_prompt", finalgate.EDGE_CASE_FEEDBACK, {}))
            if not found:
                return None
            texts: list[str] = []
            for k, text, details in found:
                gate_fired.add(k)
                log.emit(
                    "gate_feedback",
                    mechanism=k,
                    stage="final",
                    iteration=session.iteration,
                    **details,
                )
                ledger_decision("gate", k)
                texts.append(text)
            return "\n\n".join(texts)

        def escalation_force() -> str:
            return esc.strong_model if esc.enabled and esc.strong_model else "strong"

        def escalation_target() -> ModelSpec | None:
            if esc.enabled and esc.strong_model:
                return find_model(self.config.models, esc.strong_model)
            return self.router.resolve("strong")

        def switch_target() -> ModelSpec | None:
            if session.escalated or self.config.router.pin:
                return None
            t = escalation_target()
            if t is None or model_ref(t, self.config.models) == session.model_id:
                return None
            return t

        def switch_to(target: ModelSpec, trigger: str) -> None:
            prev = session.model_id
            session.escalated = True
            session.escalation_trigger = trigger
            session.model_id = model_ref(target, self.config.models)
            session.tier = target.tier
            reason = f"{trigger}_escalation"
            log.emit("route", tier=target.tier, model=target.id, score=0, reasons=[reason],
                     grade="escalated", reason=reason)
            log.emit("escalate", trigger=trigger, model=target.id, tier=target.tier,
                     from_model=prev)
            ledger_decision("escalate", f"{trigger} -> {target.tier}")
            trip.reset()
            reset_stuck()

        def cascade(trigger: str) -> bool:
            target = switch_target()
            if target is None:
                return False
            switch_to(target, trigger)
            memory.add(Message("user", ESCALATION_NOTE.format(trigger=trigger)))
            save()
            return True

        def can_escalate() -> bool:            # tripwire only
            if esc.enabled:
                allowed = policy.decide(EscalationSignals(tripwire=True)) is not None
            else:
                allowed = self.config.router.escalate_on_retry and not cheap_first
            return allowed and switch_target() is not None

        def escalate() -> None:
            kind, name, _ = trip.tripped
            strong = switch_target()
            log.emit("tripwire", action="escalate", kind=kind, tool=name, count=trip.threshold,
                     error_head=trip.head, model=strong.id)
            memory.add(Message("user", TRIPWIRE_NOTE.format(kind=kind, count=trip.threshold)))
            ledger_decision("tripwire", f"{kind} x{trip.threshold}")
            switch_to(strong, "tripwire")

        def after_step() -> bool:
            if session.iteration != seen_iter[0]:
                stuck[0] = 0 if progress[0] else stuck[0] + 1
                progress[0] = False
                seen_iter[0] = session.iteration
            if not esc.enabled or session.escalated:
                return False
            sync_budget()
            limit = gov.limits.cost_usd
            frac = gov.usage().cost_usd / limit if limit else 0.0
            trigger = policy.decide(EscalationSignals(
                stuck_iterations=stuck[0], budget_fraction=frac, check_passed=passed[0]))
            return trigger is not None and cascade(trigger)

        def stop_tripwire() -> RunResult:
            kind, name, _ = trip.tripped
            why = (
                "after one escalation to the strong tier"
                if session.escalated
                else "and no escalation to a strong tier was possible"
            )
            session.last_failure = TRIPWIRE_STOP.format(
                kind=kind, name=name, count=trip.threshold, why=why, head=trip.head
            )
            log.emit(
                "tripwire",
                action="stop",
                kind=kind,
                tool=name,
                count=trip.threshold,
                error_head=trip.head,
                escalated=session.escalated,
            )
            return stop(StopReason.TRIPWIRE)

        def handle_trip() -> RunResult | None:
            if not can_escalate():
                return stop_tripwire()
            escalate()
            save()
            return None

        async def native_step(resp: CompletionResponse) -> bool:
            if not resp.tool_calls:
                text = resp.text.strip()
                if FINAL_MARKER in text:
                    text = text.split(FINAL_MARKER, 1)[1].strip()
                memory.add(
                    Message("assistant", resp.text.strip(), extra_content=resp.extra_content)
                )
                if text:
                    refusal = final_gate()
                    if refusal is None:
                        session.final_answer = text
                        return True
                    memory.add(Message("user", refusal))
                    save()
                    return False
                memory.add(Message("user", NATIVE_EMPTY_REPLY))
                ledger_decision("empty_reply", "")
                save()
                return False
            calls = resp.tool_calls[:MAX_ACTIONS_PER_TURN]
            extra = resp.tool_calls[MAX_ACTIONS_PER_TURN:]
            memory.add(
                Message(
                    "assistant",
                    resp.text.strip(),
                    tool_calls=resp.tool_calls,
                    extra_content=resp.extra_content,
                )
            )
            session.transition(AgentState.ACTING)
            decoded = [decode_arguments(c.arguments) for c in calls]
            results: list[ToolResult | None] = [None] * len(calls)
            for i, (_, err) in enumerate(decoded):
                if err is not None:
                    results[i] = ToolResult(
                        False,
                        f"error: {err}. Call the tool again with a valid JSON object of arguments.",
                    )
            runnable = [
                (i, calls[i].name, decoded[i][0])
                for i in range(len(calls))
                if decoded[i][1] is None
            ]
            if len(runnable) == 1:
                i, name, args = runnable[0]
                results[i] = await exec_one(name, args)
            elif len(runnable) > 1:
                many = await exec_many([(name, args) for _, name, args in runnable])
                for (i, _, _), r in zip(runnable, many, strict=True):
                    results[i] = r
            limit = self.config.memory.max_observation_chars
            per = limit if len(calls) == 1 else max(200, limit // len(calls) - 64)
            for i, c in enumerate(calls):
                r = results[i]
                args = decoded[i][0]
                _log_tool(
                    log,
                    c.name,
                    args if args is not None else c.arguments,
                    r,
                    hook=self.on_tool_output,
                )
                note_tool(c.name, args, r.ok)
                ledger_tool(c.name, args, r)
                if not r.ok:
                    step_failures.append(r.output)
                if trip_on and not r.ok:
                    trip.observe("tool", c.name, r.output)
                out = r.output if len(r.output) <= per else r.output[:per] + "\n...[truncated]"
                memory.add(
                    Message("tool", out, tool_call_id=c.id),
                    read_path=read_path_of(self.ctx.workspace.root, c.name, args, r.ok),
                )
            for c in extra:
                memory.add(
                    Message(
                        "tool",
                        f"not executed: at most {MAX_ACTIONS_PER_TURN} tool calls per response",
                        tool_call_id=c.id,
                    )
                )
            note = edit_note()
            if note:
                memory.add(Message("user", note))
            session.transition(AgentState.OBSERVING)
            session.transition(AgentState.THINKING)
            save()
            return False

        off_turn: int | None = None
        explore_sem = asyncio.Semaphore(self.config.delegation.explore_concurrency)
        active = 0
        active_since = 0.0
        inflight = [0.0]

        def deleg_totals() -> tuple[int, float]:
            recs = [r for r in meter.records if r.purpose == "delegate"]
            return sum(r.input_tokens + r.output_tokens for r in recs), sum(
                r.cost_usd for r in recs
            )

        def refuse(msg: str) -> ToolResult:
            req_stats.refused += 1
            log.emit("delegate_refused", reason=msg[:200])
            return ToolResult(False, msg)

        async def delegate(task: str, mode: str = "general") -> ToolResult:
            nonlocal off_turn, active, active_since
            d = self.config.delegation
            if off_turn is not None and session.total_iterations > off_turn:
                return refuse(
                    "delegation is unavailable for the rest of this request; " + DO_IT_YOURSELF
                )
            if mode == "explore" and session.explore_calls >= d.explore_max_calls:
                return refuse(
                    f"explore limit reached ({d.explore_max_calls} per session); " + DO_IT_YOURSELF
                )
            if mode != "explore" and session.delegations >= d.max_per_session:
                return refuse(
                    f"delegation limit reached ({d.max_per_session} per session); "
                    + DO_IT_YOURSELF
                )
            tokens, cost = deleg_totals()
            if tokens >= d.max_total_tokens or cost >= d.max_total_cost_usd:
                return refuse(
                    f"delegation budget reached for this session (sub-agent tokens {tokens}/"
                    f"{d.max_total_tokens}, cost ${cost:.4f}/${d.max_total_cost_usd:.4f}); "
                    + DO_IT_YOURSELF
                )
            if mode == "explore":
                session.explore_calls += 1
                index = session.explore_calls
                req_stats.explore_calls += 1
                sub_tools = explore_registry(self.tools)
                note = EXPLORE_NOTE.format(max_chars=d.summary_max_chars)
            else:
                session.delegations += 1
                index = session.delegations
                req_stats.general_calls += 1
                sub_tools = self.tools
                note = SUBAGENT_NOTE
            turn = session.total_iterations
            sub_spec = self.router.model_for(d.model)
            hidden = self.ctx.disabled_groups | self.ctx.hidden_groups
            prompt = (
                build_system_prompt(
                    self.ctx.workspace.root,
                    sub_tools.describe(excluded_tools(sub_tools.names(), hidden), terse=terse),
                    [],
                    repo_map=repo_map,
                )
                + note
            )
            used = [0]
            seen = [0]

            async def sub_call(messages: list[Message]) -> str:
                projected = projected_cost(sub_spec, messages_tokens(messages), react_cap)
                if self._stop_requested or check_model(
                    (projected + inflight[0]) if gov.project_cost else 0.0, iterations=False
                ) is not None:
                    raise SubagentBudgetExceeded()
                if self.call_gate is not None and not self.call_gate(
                    meter.total_cost_usd + inflight[0], projected
                ):
                    log.emit(
                        "budget_gate",
                        spent_usd=meter.total_cost_usd,
                        projected_usd=projected,
                        sub=True,
                    )
                    raise SubagentBudgetExceeded()
                inflight[0] += projected
                try:
                    resp = await call_model(
                        messages, sub_spec, sub_spec.tier, "delegate", react_cap
                    )
                finally:
                    inflight[0] -= projected
                used[0] += resp.input_tokens + resp.output_tokens
                return resp.text

            def on_tool(name: str, args: Any, r: ToolResult) -> None:
                seen[0] += estimate_tokens(r.output[: self.config.memory.max_observation_chars])
                _log_tool(log, name, args, r, hook=self.on_tool_output, sub=True, mode=mode)

            async with explore_sem if mode == "explore" else contextlib.nullcontext():
                started = time.monotonic()
                if active == 0:
                    active_since = started
                active += 1
                req_stats.max_fanout = max(req_stats.max_fanout, active)
                log.emit(
                    "delegate_start",
                    index=index,
                    mode=mode,
                    model=sub_spec.id,
                    task=task[:300],
                )
                sub_ctx = replace(self.ctx, raw_file_body=False)
                try:
                    res = await run_subagent(
                        task,
                        call=sub_call,
                        tools=sub_tools,
                        ctx=sub_ctx,
                        system_prompt=prompt,
                        settings=d,
                        tokens_used=lambda: used[0],
                        cost_exceeded=lambda: (
                            gov.limits.cost_usd is not None
                            and meter.total_cost_usd + inflight[0] >= gov.limits.cost_usd
                        )
                        or (
                            self.call_gate is not None
                            and not self.call_gate(meter.total_cost_usd + inflight[0], 0.0)
                        ),
                        on_tool=on_tool,
                        max_observation_chars=self.config.memory.max_observation_chars,
                        dedupe_reads=self.config.context.dedupe_reads,
                        compress_chars=self._compress_chars(),
                        keep_last=self.config.memory.keep_last_messages,
                    )
                finally:
                    now = time.monotonic()
                    active -= 1
                    req_stats.busy_s += now - started
                    if active == 0:
                        req_stats.wall_s += now - active_since
            if res.ok:
                req_stats.ok += 1
                summary = clip_summary(res.answer or "", d.summary_max_chars)
                out = ToolResult(True, "Sub-agent summary:\n" + summary)
            else:
                req_stats.failed += 1
                off_turn = turn if off_turn is None else min(off_turn, turn)
                out = ToolResult(False, f"delegation failed ({res.reason}); " + DO_IT_YOURSELF)
            st = estimate_tokens(out.output)
            req_stats.tool_result_tokens += seen[0]
            req_stats.summary_tokens += st
            req_stats.avoided_tokens_est += max(0, seen[0] - st)
            log.emit(
                "delegate_end",
                index=index,
                mode=mode,
                ok=res.ok,
                reason=res.reason,
                steps=res.steps,
                duration_s=round(now - started, 3),
                tool_result_tokens=seen[0],
                summary_tokens=st,
            )
            save()
            return out

        run_tools = self.registry_for(delegate)
        base_tools = run_tools

        def first_arg(name: str) -> str | None:
            for s in run_tools.schemas():
                fn = s["function"]
                if fn["name"] == name:
                    return first_required_arg(fn["parameters"])
            return None

        async def decide_tier(decision: RouteDecision, force: str | None) -> RouteDecision:
            ds = self.config.decider
            if not ds.tier_routing or force or self.config.router.pin or cheap_first:
                return decision
            try:
                choice = await self.decider.choice(
                    "tier", TIERS, text=session.task, features=prompt_features(session.task)
                )
            except Exception as e:
                tag = f"decider_ignored:error:{type(e).__name__}"
                return replace(decision, reasons=decision.reasons + (tag,))
            return apply_tier_choice(decision, choice, self.router, ds.min_confidence)

        async def decide_groups(grade: str, keep: set[str]) -> frozenset[str] | None:
            ds = self.config.decider
            if not ds.toolgroup or not auto_rule_active(
                auto_simple=self.config.tool_groups.auto_simple,
                grade=grade,
                text=session.task,
                has_attachments=self._has_attachments,
            ):
                return None
            signals = request_signals(session.task, plan_mode=self.ctx.plan_mode)
            present = {group_of(n) for n in run_tools.names()}
            wanted: set[str] = set()
            for g in OPTIONAL_GROUPS:
                if (
                    g in keep
                    or g in self.ctx.disabled_groups
                    or g not in present
                    or (g == "plan-todo" and self.ctx.plan_mode)
                ):
                    if g in signals:
                        wanted.add(g)
                    continue
                try:
                    n = await self.decider.noul(
                        group_question(g),
                        text=session.task,
                        features={"plan_mode": self.ctx.plan_mode},
                    )
                    yes = n.yes if accepted(n, ds.min_confidence) else g in signals
                except Exception:
                    yes = g in signals
                if yes:
                    wanted.add(g)
            return frozenset(wanted)

        async def hint(question: str, text: str, features: dict) -> None:
            if not self.config.decider.sensor_hint:
                return
            with contextlib.suppress(Exception):
                await self.decider.noul(question, text=text, features=features)

        async def hint_stuck() -> None:
            if not step_failures:
                return
            last, count = step_failures[-1], len(step_failures)
            step_failures.clear()
            await hint(
                "stuck",
                normalize_error(last),
                {"failures": count, "streak": trip.streak, "threshold": trip.threshold},
            )

        async def hint_complete() -> None:
            answer = session.final_answer or ""
            await hint(
                "complete",
                f"Task: {session.task[:1000]}\nFinal answer: {answer[:2000]}",
                {
                    "has_answer": bool(answer.strip()),
                    "has_check": session.check_command is not None,
                },
            )

        def tamper_files() -> list[str]:
            if not session.test_hashes:
                return []
            return tampered_tests(self.ctx.workspace.root, session.test_hashes)

        async def run_selftest() -> None:
            if not (self.ctx.workspace.root / SELFTEST_DIR).is_dir():
                session.selftest_result = {"ran": False, "reason": "no_tests"}
                log.emit("selftest", ran=False, reason="no_tests")
                return
            verdict = (gate.check("run_shell", {"command": SELFTEST_COMMAND},
                                  approval_mode_of(self.ctx.approval))
                       if gate is not None else None)
            if verdict is not None and verdict.blocked:
                session.selftest_result = {"ran": False, "reason": "policy"}
                log.emit("selftest", ran=False, reason="policy", policy=verdict.rule)
                return
            try:
                res = await RunShellTool().run({"command": SELFTEST_COMMAND}, self.ctx)
            except OSError as e:
                res = ToolResult(False, f"error: {e}")
            tail = res.output[-self.config.agent.sensor_feedback_chars:]
            session.selftest_result = {
                "ran": True,
                "ok": res.ok,
                "feedback": "" if res.ok else tail,
            }
            log.emit("selftest", ran=True, ok=res.ok, command=SELFTEST_COMMAND,
                     output_head=res.output[-500:])
            if not res.ok:
                memory.add(
                    Message(
                        "user",
                        SELFTEST_FEEDBACK.format(
                            command=SELFTEST_COMMAND, chars=len(tail), output=tail
                        ),
                    )
                )

        async def sensor_gate() -> RunResult | None:
            command = session.check_command
            if self.before_check is not None:
                self.before_check()
            mode = approval_mode_of(self.ctx.approval)
            verdict = (gate.check("run_shell", {"command": command}, mode)
                       if gate is not None else None)
            if verdict is not None and verdict.blocked:
                session.check_runs += 1
                log.emit("check", command=command, ok=False,
                         output_head=verdict.message[-500:], sensor=True,
                         run=session.check_runs, policy=verdict.rule)
                ledger_check(command, False, verdict.message)
                ledger_decision("check_blocked", verdict.rule)
                session.last_failure = verdict.message
                session.transition(AgentState.FAILED)
                session.stop_reason = StopReason.CHECK_FAILED.value
                log.emit("stop", reason=StopReason.CHECK_FAILED.value,
                         check_runs=session.check_runs)
                save()
                return RunResult(session, session.final_answer, StopReason.CHECK_FAILED,
                                 result_summary(), log.path)
            tamper = tamper_files()
            if tamper:
                res = ToolResult(False, TESTS_MODIFIED.format(files=", ".join(tamper)))
            else:
                try:
                    res = await RunShellTool().run({"command": command}, self.ctx)
                except OSError as e:
                    res = ToolResult(False, f"error: {e}")
            session.check_runs += 1
            log.emit(
                "check",
                command=command,
                ok=res.ok,
                output_head=res.output[-500:],
                sensor=True,
                run=session.check_runs,
                **({"reason": "tests_modified", "files": tamper} if tamper else {}),
            )
            ledger_check(command, res.ok, res.output)
            if tamper:
                ledger_decision(
                    "tests_modified",
                    ", ".join(mask_path(self.ctx.workspace.root, lguard(), f) or PROTECTED_MARK
                              for f in tamper),
                )
            if res.ok:
                passed[0] = True
                return finish()
            tail = res.output[-self.config.agent.sensor_feedback_chars :]
            session.last_failure = tail
            tripped = trip.observe("check", "check", res.output)
            max_runs = self.config.agent.sensor_max_retries + 1
            if session.check_runs - session.escalated_at_check >= max_runs:
                if self.config.agent.ladder and not session.ladder_reflected:
                    session.ladder_reflected = True
                    log.emit("ladder_reflect", check_runs=session.check_runs)
                    session.transition(AgentState.REFLECTING)
                    save()
                    return None
                if self.config.agent.ladder and not session.ladder_exhausted:
                    session.ladder_exhausted = True
                    log.emit("ladder_exhausted", check_runs=session.check_runs,
                             reflections=len(session.reflections))
                    if policy.decide(EscalationSignals(ladder_exhausted=True)) and cascade(
                        "ladder_exhausted"
                    ):
                        session.escalated_at_check = session.check_runs
                        session.sensor_retries += 1
                        memory.add(Message("user", SENSOR_FEEDBACK.format(
                            run=session.check_runs,
                            max_runs=session.escalated_at_check + max_runs,
                            command=command, chars=len(tail), output=tail)))
                        session.final_answer = None
                        session.transition(AgentState.THINKING)
                        reset_stuck()
                        save()
                        return None
                session.transition(AgentState.FAILED)
                session.stop_reason = StopReason.CHECK_FAILED.value
                log.emit(
                    "stop",
                    reason=StopReason.CHECK_FAILED.value,
                    check_runs=session.check_runs,
                )
                save()
                return RunResult(
                    session,
                    session.final_answer,
                    StopReason.CHECK_FAILED,
                    result_summary(),
                    log.path,
                )
            if tripped:
                out = handle_trip()
                if out is not None:
                    return out
            session.sensor_retries += 1
            memory.add(
                Message(
                    "user",
                    SENSOR_FEEDBACK.format(
                        run=session.check_runs,
                        max_runs=session.escalated_at_check + max_runs,
                        command=command,
                        chars=len(tail),
                        output=tail,
                    ),
                )
            )
            session.final_answer = None
            reset_stuck()
            session.transition(AgentState.THINKING)
            save()
            return None

        try:
            while True:
                run_tools = await self._with_mcp(base_tools)
                if session.state == AgentState.ROUTING:
                    retry = (session.attempt > 0 and self.config.router.escalate_on_retry
                             and not session.ladder_reflected)
                    if esc.enabled:
                        force = escalation_force() if (session.escalated or retry) else None
                    elif cheap_first:
                        force = None
                    else:
                        force = "strong" if retry else None
                    prev_model = session.model_id
                    decision = self.router.route(session.task, force)
                    decision = await decide_tier(decision, force)
                    session.model_id = model_ref(decision.model, self.config.models)
                    session.tier = decision.tier
                    log.emit(
                        "route",
                        tier=decision.tier,
                        model=decision.model.id,
                        score=decision.score,
                        reasons=list(decision.reasons),
                        grade=decision.grade,
                        reason=decision.reason_line,
                    )
                    if (retry and force is not None and not session.escalated
                            and prev_model is not None and session.model_id != prev_model):
                        session.escalation_trigger = "attempt"
                        if esc.enabled:
                            session.escalated = True
                        log.emit("escalate", trigger="attempt", model=decision.model.id,
                                 tier=decision.tier, from_model=prev_model)
                    keep = set(session.tool_groups) | self.ctx.forced_groups
                    wanted = await decide_groups(decision.grade, keep)
                    self.ctx.hidden_groups = auto_hidden_groups(
                        auto_simple=self.config.tool_groups.auto_simple,
                        grade=decision.grade,
                        text=session.task,
                        has_attachments=self._has_attachments,
                        plan_mode=self.ctx.plan_mode,
                        keep=keep,
                        wanted=wanted,
                    )
                    sync_groups()
                    if self.ctx.hidden_groups:
                        log.emit(
                            "tool_groups",
                            hidden=sorted(self.ctx.hidden_groups),
                            disabled=sorted(self.ctx.disabled_groups),
                        )
                    log.emit(
                        "attempt_start",
                        attempt=session.attempt,
                        protocol=effective_protocol(self.config, decision.model),
                        system_prompt=system_prompt(
                            effective_protocol(self.config, decision.model)
                        ),
                    )
                    seen_reads.clear()
                    reset_stuck()
                    session.transition(AgentState.THINKING)
                    save()

                spec = self._spec(session.model_id, session.tier)
                protocol = effective_protocol(self.config, spec)
                session.model_id = model_ref(spec, self.config.models)
                tier = session.tier or spec.tier

                if session.state == AgentState.THINKING:
                    while True:
                        if self._stop_requested:
                            return stop(StopReason.INTERRUPTED)
                        if after_step():
                            spec = self._spec(session.model_id, session.tier)
                            protocol = effective_protocol(self.config, spec)
                            tier = session.tier or spec.tier
                        cap = check_model()
                        if cap is not None:
                            return budget_stop(cap)
                        msgs = memory.build(system_prompt(protocol))
                        await after_build()
                        tools = (
                            run_tools.schemas(excluded(), terse=terse)
                            if protocol == "native"
                            else None
                        )
                        if gov.project_cost:
                            cap = check_model(projected_for(msgs, spec, tools))
                            if cap is not None:
                                return budget_stop(cap)
                        if not gate_ok(msgs, spec, tools):
                            return stop(StopReason.COST_LIMIT)
                        if protocol == "native":
                            self.ctx.raw_file_body = False
                            resp = await call_model(
                                msgs, spec, tier, "react", react_cap, tools
                            )
                            session.iteration += 1
                            session.total_iterations += 1
                            gov.add_iteration()
                            if await native_step(resp):
                                break
                            await hint_stuck()
                            if trip.tripped is not None:
                                out = handle_trip()
                                if out is not None:
                                    return out
                                spec = self._spec(session.model_id, session.tier)
                                protocol = effective_protocol(self.config, spec)
                                tier = session.tier or spec.tier
                            continue
                        self.ctx.raw_file_body = self.config.agent.raw_file_body
                        rresp = await call_model(
                            msgs,
                            spec,
                            tier,
                            "react",
                            react_cap,
                            temperature=REPEAT_TEMPERATURE if boost[0] else 0.0,
                        )
                        boost[0] = False
                        text = rresp.text
                        session.iteration += 1
                        session.total_iterations += 1
                        gov.add_iteration()
                        truncated = rresp.finish_reason == "length" or (
                            rresp.finish_reason is None and rresp.output_tokens >= react_cap
                        )
                        turn = parse_turn(
                            text,
                            lenient=self.config.agent.lenient_parse,
                            first_arg=first_arg,
                            json_strings=self.config.agent.json_string_repair,
                            raw_blocks=self.config.agent.raw_file_body,
                            located=self.config.agent.located_errors,
                            truncated=truncated,
                        )
                        memory.add(
                            Message(
                                "assistant",
                                text.split("\nObservation:")[0].strip(),
                                extra_content=rresp.extra_content,
                            )
                        )
                        rejected = turn.error is not None or any(c.args is None for c in turn.calls)
                        if turn.repaired:
                            log.emit(
                                "parse_repaired",
                                repairs=list(turn.repaired),
                                iteration=session.iteration,
                            )
                        if turn.final_answer is not None:
                            refusal = final_gate()
                            if refusal is None:
                                session.final_answer = turn.final_answer
                                break
                            memory.add(
                                Message(
                                    "user",
                                    with_note(f"Observation: {refusal}", repeat_note(text, None)),
                                )
                            )
                            save()
                            continue
                        if truncated and rejected:
                            count_unparsed(text)
                            cause = None
                            if self.config.agent.located_errors:
                                first = located_input_error(
                                    text, raw_hint=self.config.agent.raw_file_body
                                ).split("\n")[0]
                                if first != INPUT_ERROR + ".":
                                    cause = first
                            msg = truncated_error(
                                react_cap,
                                located=self.config.agent.located_errors,
                                cause=cause,
                            )
                            log.emit(
                                "reply_truncated",
                                iteration=session.iteration,
                                output_tokens=rresp.output_tokens,
                                max_tokens=react_cap,
                            )
                            ledger_decision("reply_truncated", f"{rresp.output_tokens} tokens")
                            log.emit("parse_error", error=msg, iteration=session.iteration)
                            memory.add(
                                Message(
                                    "user",
                                    with_note(
                                        f"Observation: {msg}",
                                        repeat_note(text, ("parse_error", None)),
                                    ),
                                )
                            )
                            save()
                            continue
                        if turn.error:
                            count_unparsed(text)
                            log.emit("parse_error", error=turn.error, iteration=session.iteration)
                            ledger_decision("parse_error", turn.error)
                            memory.add(
                                Message(
                                    "user",
                                    with_note(
                                        f"Observation: {turn.error}",
                                        repeat_note(text, ("parse_error", None)),
                                    ),
                                )
                            )
                            save()
                            continue
                        session.transition(AgentState.ACTING)
                        read_path: str | None = None
                        if len(turn.calls) == 1:
                            c = turn.calls[0]
                            res = await exec_one(c.name, c.args)
                            _log_tool(log, c.name, c.args, res, hook=self.on_tool_output)
                            note_tool(c.name, c.args, res.ok)
                            ledger_tool(c.name, c.args, res)
                            if not res.ok:
                                step_failures.append(res.output)
                            if trip_on and not res.ok:
                                trip.observe("tool", c.name, res.output)
                            observation = f"Observation: {res.output}"
                            read_path = read_path_of(
                                self.ctx.workspace.root, c.name, c.args, res.ok
                            )
                        else:
                            results = await exec_many([(c.name, c.args) for c in turn.calls])
                            for c, r in zip(turn.calls, results, strict=True):
                                _log_tool(log, c.name, c.args, r, hook=self.on_tool_output)
                                note_tool(c.name, c.args, r.ok)
                                ledger_tool(c.name, c.args, r)
                                if not r.ok:
                                    step_failures.append(r.output)
                                if trip_on and not r.ok:
                                    trip.observe("tool", c.name, r.output)
                            observation = _multi_observation(
                                [c.name for c in turn.calls],
                                results,
                                self.config.memory.max_observation_chars,
                                turn.dropped,
                            )
                        note = edit_note()
                        if note:
                            observation = f"{observation}\n{note}"
                        if len(turn.calls) == 1:
                            failure = edit_mismatch([c], [res])
                        else:
                            failure = edit_mismatch(turn.calls, results)
                        observation = with_note(observation, repeat_note(text, failure))
                        session.transition(AgentState.OBSERVING)
                        memory.add(Message("user", observation), read_path=read_path)
                        session.transition(AgentState.THINKING)
                        save()
                        await hint_stuck()
                        if trip.tripped is not None:
                            out = handle_trip()
                            if out is not None:
                                return out
                            spec = self._spec(session.model_id, session.tier)
                            protocol = effective_protocol(self.config, spec)
                            tier = session.tier or spec.tier
                    await hint_complete()
                    if session.check_command is None:
                        if session.selftest and not self.ctx.plan_mode:
                            await run_selftest()
                        return finish()
                    if session.sensor and self.ctx.plan_mode:
                        log.emit("check_skipped", reason="plan_mode")
                        return finish()
                    session.transition(AgentState.CHECKING)

                if session.state == AgentState.CHECKING and session.sensor:
                    out = await sensor_gate()
                    if out is not None:
                        return out
                    continue

                if session.state == AgentState.CHECKING:
                    tamper = tamper_files()
                    if tamper:
                        res = ToolResult(False, TESTS_MODIFIED.format(files=", ".join(tamper)))
                    else:
                        res = await self.tools.execute(
                            "run_shell",
                            {"command": session.check_command},
                            self.ctx,
                        )
                    log.emit(
                        "check",
                        command=session.check_command,
                        ok=res.ok,
                        output_head=res.output[-500:],
                        **({"reason": "tests_modified", "files": tamper} if tamper else {}),
                    )
                    ledger_check(session.check_command, res.ok, res.output)
                    if res.ok:
                        passed[0] = True
                        return finish()
                    session.last_failure = res.output[-2000:]
                    if session.attempt + 1 < self.config.agent.max_attempts:
                        session.transition(AgentState.REFLECTING)
                        save()
                    else:
                        session.transition(AgentState.FAILED)
                        session.stop_reason = StopReason.CHECK_FAILED.value
                        log.emit("stop", reason=StopReason.CHECK_FAILED.value)
                        save()
                        return RunResult(
                            session,
                            session.final_answer,
                            StopReason.CHECK_FAILED,
                            result_summary(),
                            log.path,
                        )

                if session.state == AgentState.REFLECTING:
                    if self._stop_requested:
                        return stop(StopReason.INTERRUPTED)
                    cap = check_model(iterations=False)
                    if cap is not None:
                        return budget_stop(cap)
                    if gov.project_cost:
                        cap = check_model(
                            projected_call_cost(
                                spec,
                                messages_tokens(flatten_tool_messages(memory.recent)),
                                REFLECT_MAX_TOKENS,
                            ),
                            iterations=False,
                        )
                        if cap is not None:
                            return budget_stop(cap)
                    if not gate_ok([], spec, None):
                        return stop(StopReason.COST_LIMIT)
                    reflection = await reflect(
                        partial(
                            call_llm,
                            spec=spec,
                            tier=tier,
                            purpose="reflect",
                            max_tokens=REFLECT_MAX_TOKENS,
                        ),
                        session.task,
                        flatten_tool_messages(memory.recent),
                        session.last_failure or "",
                        max_sentences=5 if session.ladder_reflected else None,
                    )
                    session.reflections.append(reflection)
                    self.store.append(
                        session.id,
                        "reflection",
                        {"attempt": session.attempt, "text": reflection},
                    )
                    log.emit("reflection", attempt=session.attempt, text=reflection)
                    ledger_decision("reflection", reflection)
                    session.attempt += 1
                    session.iteration = 0
                    gov.new_attempt()
                    session.final_answer = None
                    session.last_failure = None
                    prev_ledger = memory.ledger
                    memory = self._new_memory(session.id)
                    if prev_ledger is not None:
                        memory.ledger = prev_ledger
                    memory.pin(Message("user", f"Task: {session.task}"))
                    session.transition(AgentState.ROUTING)
                    save()
        except ProviderTimeout as e:
            if e.wall_limited:
                return budget_stop("wall")
            log.emit("provider_timeout", model=e.model, timeout_s=e.timeout_s, attempts=e.attempts)
            return stop(StopReason.PROVIDER_TIMEOUT)
        except BaseException:
            save()
            raise

    def compact(self, session: Session, keep: int = 2) -> int:
        memory = WorkingMemory.from_dict(session.memory, self.config.memory, self.store, session.id)
        n = memory.compact(keep)
        session.memory = memory.to_dict()
        self.sessions.save(session)
        return n
