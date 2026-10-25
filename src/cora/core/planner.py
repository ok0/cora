from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from cora.core.budget import BudgetGovernor, projected_call_cost
from cora.core.config import CoraConfig
from cora.core.errors import CoraError
from cora.core.metering import CostMeter
from cora.core.milestones import PlanError, ProjectPlan, parse_plan
from cora.core.outcome import OUTCOME_KEYS
from cora.core.providers import ProviderPool
from cora.core.providers.base import call_with_timeout
from cora.core.react import _block_end, _swap_quotes
from cora.core.router import HeuristicRouter
from cora.core.types import CompletionRequest, Message, messages_tokens

PLAN_MAX_TOKENS = 2000
PLAN_REPAIRS = ("strip_fences", "extract_object", "trailing_commas", "single_quotes")
PLAN_DOC_KEYS = (*(k for k in OUTCOME_KEYS if k != "profile"), "path", "goal", "milestone_count")

PLANNER_SYSTEM = (
    "You are a project planner. Break the user's goal into an ordered list of milestones.\n"
    "Reply with ONE JSON object and nothing else, of this shape:\n"
    '{{"goal": str, "milestones": [{{"id": str, "title": str, "task": str, "check": str, '
    '"conditions": [{{"kind": "command", "cmd": str}}, '
    '{{"kind": "file_exists", "path": str}}]}}]}}\n'
    '"check" and "conditions" are optional.\n'
    "Rules:\n"
    "- Use 1 to {max} milestones, listed in execution order.\n"
    "- Every id is unique and non-empty.\n"
    "- Every task is non-empty and self-contained, because each milestone runs in a fresh "
    "session.\n"
    "- Prefer conditions that are cheap, deterministic and side-effect free.\n"
    '- "check" is a single runnable shell command that exits 0 when the milestone is done; '
    'omit it if no such command exists, and use "conditions" for deterministic checks.\n'
    '- A "path" is relative to the workspace: no absolute paths and no "..".\n'
    "- Use no other keys."
)


class PlanBudgetExceeded(CoraError):
    def __init__(self, cap: str) -> None:
        self.cap = cap
        super().__init__(f"budget exceeded before plan generation: {cap} cap reached")


def plan_messages(goal: str, max_milestones: int) -> list[Message]:
    return [
        Message("system", PLANNER_SYSTEM.format(max=max_milestones)),
        Message("user", f"Goal:\n{goal}"),
    ]


def repair_messages(messages: list[Message], reply: str, error: str) -> list[Message]:
    return [
        *messages,
        Message("assistant", reply[:4000]),
        Message(
            "user",
            f"Your reply was invalid: {error}\nReply again with only the corrected JSON object.",
        ),
    ]


def _json_error(e: json.JSONDecodeError) -> PlanError:
    return PlanError(f"model reply is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})")


def _strip_fence_lines(s: str) -> str:
    return re.sub(r"(?m)^[ \t]*```[A-Za-z0-9_-]*[ \t]*\n?", "", s)


def _extract_object(s: str) -> str:
    b = s.find("{")
    if b == -1:
        return s
    e = _block_end(s, b, '"')
    if e == -1:
        return s
    return s[b:e]


def _drop_trailing_commas(s: str) -> str:
    out: list[str] = []
    dq = False
    k = 0
    while k < len(s):
        c = s[k]
        if dq:
            out.append(c)
            if c == "\\" and k + 1 < len(s):
                out.append(s[k + 1])
                k += 2
                continue
            if c == '"':
                dq = False
        elif c == '"':
            dq = True
            out.append(c)
        elif c == ",":
            n = k + 1
            while n < len(s) and s[n].isspace():
                n += 1
            if not (n < len(s) and s[n] in "}]"):
                out.append(c)
        else:
            out.append(c)
        k += 1
    return "".join(out)


def _single_to_double(s: str) -> str:
    out = _swap_quotes(s)
    return s if out is None else out


def lenient_plan_json(text: str) -> tuple[Any, tuple[str, ...]] | None:
    fns = {
        "strip_fences": _strip_fence_lines,
        "extract_object": _extract_object,
        "trailing_commas": _drop_trailing_commas,
        "single_quotes": _single_to_double,
    }
    cur = text.strip()
    applied: list[str] = []
    for name in PLAN_REPAIRS:
        new = fns[name](cur)
        if new == cur:
            continue
        cur = new
        applied.append(name)
        try:
            data = json.loads(cur)
        except json.JSONDecodeError:
            continue
        return data, tuple(applied)
    return None


def _decode_reply(s: str, e: json.JSONDecodeError, lenient: bool) -> Any:
    fenced = re.search(r"```(?:json|JSON)?\s*\n?(.*?)```", s, re.S)
    if fenced is not None:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError as e2:
            e = e2
    if lenient:
        r = lenient_plan_json(s)
        if r is not None:
            return r[0]
    raise _json_error(e) from e


def plan_from_text(text: str, *, max_milestones: int, lenient: bool = False) -> ProjectPlan:
    s = text.strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        data = _decode_reply(s, e, lenient)
    if not isinstance(data, dict):
        raise PlanError("model reply must be a JSON object")
    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise PlanError("model reply: 'goal' must be a non-empty string")
    raw = data.get("milestones")
    if isinstance(raw, list) and len(raw) > max_milestones:
        raise PlanError(f"model reply: too many milestones: {len(raw)} (max {max_milestones})")
    try:
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        raise PlanError("model reply contains invalid unicode") from None
    return parse_plan(data, "from model reply")


async def plan_project(
    goal: str,
    call: Callable[[list[Message]], Awaitable[str]],
    *,
    max_milestones: int = 8,
    lenient: bool = False,
) -> ProjectPlan:
    msgs = plan_messages(goal, max_milestones)
    reply = await call(msgs)
    try:
        return plan_from_text(reply, max_milestones=max_milestones, lenient=lenient)
    except PlanError as e1:
        reply2 = await call(repair_messages(msgs, reply, str(e1)))
        try:
            return plan_from_text(reply2, max_milestones=max_milestones, lenient=lenient)
        except PlanError as e2:
            raise PlanError(f"planner reply invalid after one repair attempt: {e2}") from e2


async def generate_plan(
    goal: str,
    config: CoraConfig,
    governor: BudgetGovernor,
    *,
    meter: CostMeter,
    max_milestones: int,
    providers: ProviderPool | None = None,
) -> tuple[ProjectPlan, dict]:
    spec = HeuristicRouter(config).model_for(config.router.default)
    provider = (providers or ProviderPool(config)).get(spec.provider)
    calls = 0

    async def call(msgs: list[Message]) -> str:
        nonlocal calls
        projected = projected_call_cost(spec, messages_tokens(msgs), PLAN_MAX_TOKENS)
        cap = governor.check_model_call(
            projected if governor.project_cost else 0.0, iterations=False
        )
        if cap:
            raise PlanBudgetExceeded(cap)
        started = time.monotonic()
        resp = await call_with_timeout(
            lambda: provider.complete(CompletionRequest(spec.id, msgs, PLAN_MAX_TOKENS, 0.0)),
            model=spec.id,
            timeout_s=config.agent.call_timeout_s,
        )
        latency = time.monotonic() - started
        rec = meter.record(
            spec,
            spec.tier,
            "plan",
            resp.input_tokens,
            resp.output_tokens,
            cost_usd=resp.cost_usd,
            cached_input_tokens=resp.cached_input_tokens,
            latency_s=latency,
        )
        governor.add_cost(rec.cost_usd)
        calls += 1
        return resp.text

    plan = await plan_project(
        goal, call, max_milestones=max_milestones, lenient=config.agent.lenient_parse
    )
    info = {
        "model": spec.id,
        "calls": calls,
        "cost_usd": meter.total_cost_usd,
        "tokens_in": sum(r.input_tokens for r in meter.records),
        "tokens_out": sum(r.output_tokens for r in meter.records),
    }
    return plan, info


def _plan_doc(
    meter: CostMeter,
    governor: BudgetGovernor | None,
    *,
    ok: bool,
    stop_reason: str,
    wall_s: float,
    warnings: Sequence[str],
    errors: Sequence[str],
    code: int,
    path: Path | None,
    goal: str,
    milestone_count: int,
) -> dict:
    models: list[str] = []
    for r in meter.records:
        if r.model not in models:
            models.append(r.model)
    return {
        "ok": ok,
        "stop_reason": stop_reason,
        "final_answer": None,
        "session_id": None,
        "iterations": 0,
        "cost_usd": meter.total_cost_usd,
        "tokens": {
            "in": sum(r.input_tokens for r in meter.records),
            "out": sum(r.output_tokens for r in meter.records),
        },
        "wall_s": round(wall_s, 3),
        "models": models,
        "tools": {},
        "policy": None,
        "budget": governor.to_dict() if governor else None,
        "warnings": list(warnings),
        "errors": list(errors),
        "exit_code": code,
        "path": str(path) if path is not None else None,
        "goal": goal,
        "milestone_count": milestone_count,
    }


def plan_outcome(
    path: Path,
    plan: ProjectPlan,
    meter: CostMeter,
    governor: BudgetGovernor | None,
    *,
    wall_s: float,
    warnings: Sequence[str] = (),
) -> dict:
    return _plan_doc(
        meter,
        governor,
        ok=True,
        stop_reason="final_answer",
        wall_s=wall_s,
        warnings=warnings,
        errors=(),
        code=0,
        path=path,
        goal=plan.goal,
        milestone_count=len(plan.milestones),
    )


def plan_error_outcome(
    message: str,
    code: int,
    *,
    goal: str,
    meter: CostMeter,
    governor: BudgetGovernor | None,
    wall_s: float,
    warnings: Sequence[str] = (),
    stop_reason: str = "error",
) -> dict:
    return _plan_doc(
        meter,
        governor,
        ok=False,
        stop_reason=stop_reason,
        wall_s=wall_s,
        warnings=warnings,
        errors=[message],
        code=code,
        path=None,
        goal=goal,
        milestone_count=0,
    )
