from __future__ import annotations

import dataclasses
import json
import os
import re
import shlex
import time
from collections.abc import Awaitable, Callable, Collection, Sequence
from pathlib import Path
from typing import Any

from cora.core.budget import BudgetGovernor, projected_call_cost
from cora.core.config import CoraConfig, secret_env_names
from cora.core.errors import CoraError
from cora.core.memory import scrub_secrets
from cora.core.metering import CostMeter
from cora.core.milestones import PlanError, ProjectPlan, parse_plan
from cora.core.outcome import OUTCOME_KEYS
from cora.core.policy import GateVerdict, PlanPolicy, hint_for
from cora.core.providers import ProviderPool
from cora.core.providers.base import call_with_timeout
from cora.core.react import _block_end, _swap_quotes
from cora.core.router import HeuristicRouter
from cora.core.types import CompletionRequest, Message, messages_tokens

PLAN_MAX_TOKENS = 2000
PLAN_REPAIRS = ("strip_fences", "extract_object", "trailing_commas", "single_quotes")
PLAN_REJECT_MAX_CHARS = 20000
UNDERIVED_RULE = "plan:underived-path"
UNDERIVED_HINT = (
    "the file is neither named in the goal nor present in the workspace; "
    "check only files the goal names or that already exist"
)
WORKSPACE_LIST_MAX = 200
SELECTOR_RULE = "plan:underived-selector"
SELECTOR_HINT = (
    "the test selector matches no test that exists in the workspace or that the goal names; "
    "select existing tests or remove the selector"
)
PLAN_RULES = (UNDERIVED_RULE, SELECTOR_RULE)
TEST_IDENT_RE = re.compile(r"\b[Tt]est\w*")
BARE_NAME_RE = re.compile(r"(?:\./)?[\w-]+(?:\.[\w-]+)*\.[A-Za-z][\w-]*")
SEGMENT_SEPS = frozenset({"&&", "||", "|", ";"})
TEST_FILE_MAX_CHARS = 200_000
GOAL_PATHS_RULE = (
    '\n- Every "path" of a file_exists condition and every file path a "check" or "command" '
    'names must be named in the goal or listed under "Files already in the workspace". Do not '
    "check files that only your own plan introduces. A test selector in a \"check\" or "
    '"command" must match a test that already exists in the workspace or that the goal names.'
)
REPAIR_HINTS = {
    "empty": "Your reply was empty.",
    "truncated": (
        "Your reply was cut off before the JSON object ended. Keep the plan shorter: fewer "
        "milestones, shorter tasks and fewer conditions."
    ),
    "no_object": "Your reply contained no JSON object.",
    "prose_or_fence": "Your reply had text or code fences around the JSON object.",
}
PLAN_DOC_KEYS = (
    *(k for k in OUTCOME_KEYS if k != "profile"),
    "path",
    "goal",
    "milestone_count",
    "plan_policy",
)
POLICY_RULES_HEADER = 'Shell policy for "check" and "command" conditions:\n'
UNGATED_WARNING = (
    "warning: milestone '{id}' is ungated: every check was denied by the run's policy "
    "and dropped; it runs without a check"
)

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


def plan_messages(
    goal: str,
    max_milestones: int,
    *,
    policy_rules: str | None = None,
    workspace_files: Sequence[str] | None = None,
) -> list[Message]:
    system = PLANNER_SYSTEM.format(max=max_milestones)
    user = f"Goal:\n{goal}"
    if workspace_files is not None:
        system += GOAL_PATHS_RULE
        user += "\n\nFiles already in the workspace:\n" + "\n".join(
            workspace_files[:WORKSPACE_LIST_MAX]
        )
        if len(workspace_files) > WORKSPACE_LIST_MAX:
            user += f"\n... ({len(workspace_files) - WORKSPACE_LIST_MAX} more)"
        elif not workspace_files:
            user += "\n(none)"
    if policy_rules is not None:
        system += "\n" + POLICY_RULES_HEADER + policy_rules
    return [
        Message("system", system),
        Message("user", user),
    ]


def workspace_listing(root: Path) -> list[str]:
    out: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def workspace_test_names(root: Path, files: Sequence[str]) -> list[str]:
    names: set[str] = set()
    test_files = [rel for rel in files if "test" in rel.rsplit("/", 1)[-1].lower()]
    for rel in test_files[:WORKSPACE_LIST_MAX]:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names.add(rel.lower())
        for ident in set(TEST_IDENT_RE.findall(text[:TEST_FILE_MAX_CHARS])):
            names.add(f"{rel}::{ident}".lower())
    return sorted(names)


@dataclasses.dataclass(frozen=True)
class PolicyIssue:
    milestone_id: str
    field: str
    command: str
    rule: str
    hint: str

    def dropped(self) -> dict:
        return {
            "milestone": self.milestone_id,
            "field": self.field,
            "command": self.command,
            "rule": self.rule,
        }


def validate_plan_policy(plan: ProjectPlan, policy: PlanPolicy) -> list[PolicyIssue]:
    issues: list[PolicyIssue] = []
    for m in plan.milestones:
        if m.check:
            v: GateVerdict = policy.verdict(m.check)
            if v.blocked:
                issues.append(PolicyIssue(m.id, "check", m.check, v.rule, hint_for(v)))
        for i, c in enumerate(m.conditions):
            if c.kind != "command":
                continue
            command = c.cmd or ""
            v = policy.verdict(command)
            if v.blocked:
                issues.append(PolicyIssue(m.id, f"conditions[{i}]", command, v.rule, hint_for(v)))
    return issues


def _issue_bullets(issues: list[PolicyIssue]) -> str:
    return "\n".join(
        f"- milestone {i.milestone_id} {i.field}: {i.command} (rule {i.rule}: {i.hint})"
        for i in issues
    )


def policy_repair_messages(
    messages: list[Message], reply: str, issues: list[PolicyIssue]
) -> list[Message]:
    body = (
        "Some commands in your plan are denied by this run's shell policy and would never run:\n"
        + _issue_bullets(issues)
        + "\nReply again with the corrected full plan as one JSON object. Replace each denied "
        "command with one the policy allows, or remove it."
    )
    return [*messages, Message("assistant", reply[:4000]), Message("user", body)]


def plan_repair_messages(
    messages: list[Message], reply: str, issues: list[PolicyIssue]
) -> list[Message]:
    body = (
        "Some checks or conditions in your plan cannot be used:\n"
        + _issue_bullets(issues)
        + "\nReply again with the corrected full plan as one JSON object. Replace each listed "
        "item with one that is allowed and checks only what the goal names, or remove it."
    )
    return [*messages, Message("assistant", reply[:4000]), Message("user", body)]


def _derived(p: str, goal: str, existing: Collection[str]) -> bool:
    q = p.removeprefix("./").rstrip("/")
    if q in goal or q in existing:
        return True
    return any(e.startswith(q + "/") for e in existing)


def _selector_suffix(test_names: Collection[str]) -> str:
    ids = sorted({n.split("::", 1)[1] for n in test_names if "::" in n})[:20]
    if not ids:
        return " (no tests exist yet)"
    return " (existing tests: " + ", ".join(ids) + ")"


def _command_issue(
    command: str,
    goal: str,
    existing: Collection[str],
    names: Collection[str],
    goal_idents: Collection[str],
    suffix: str,
) -> tuple[str, str] | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = [[]]
    for t in tokens:
        if t in SEGMENT_SEPS:
            segments.append([])
        else:
            segments[-1].append(t)
    for seg in segments:
        for j, tok in enumerate(seg):
            cand = tok.split("::", 1)[0]
            if (
                ":" not in cand
                and re.fullmatch(r"(?:\./)?(?:[\w.-]+/)+[\w.-]*", cand)
                and not _derived(cand, goal, existing)
            ):
                return UNDERIVED_RULE, UNDERIVED_HINT
            if (
                j > 0
                and not tok.startswith("-")
                and ":" not in cand
                and "/" not in cand
                and BARE_NAME_RE.fullmatch(cand)
                and not _derived(cand, goal, existing)
                and not any(cand in e.replace("/", ".") for e in existing)
            ):
                return UNDERIVED_RULE, UNDERIVED_HINT
            expr: str | None = None
            if tok == "-k":
                if j + 1 < len(seg):
                    expr = seg[j + 1]
            elif tok.startswith("-k") and len(tok) > 2 and not tok.startswith("--"):
                expr = tok[2:]
            if expr is None or not any(
                not t.startswith("-") and "test" in t.lower() for t in seg[:j]
            ):
                continue
            words = re.findall(r"[A-Za-z_][\w\[\].-]*", expr)
            if "not" in words:
                continue
            for w in words:
                if w in ("and", "or"):
                    continue
                wl = w.lower()
                if not (any(wl in n for n in names) or any(wl in g for g in goal_idents)):
                    return SELECTOR_RULE, SELECTOR_HINT + suffix
    return None


def validate_plan_paths(
    plan: ProjectPlan,
    goal: str,
    existing: Collection[str],
    test_names: Collection[str] = (),
) -> list[PolicyIssue]:
    names = [n.lower() for n in test_names]
    goal_idents = [i.lower() for i in TEST_IDENT_RE.findall(goal)]
    suffix = _selector_suffix(test_names)
    issues: list[PolicyIssue] = []
    for m in plan.milestones:
        for i, c in enumerate(m.conditions):
            if c.kind == "file_exists" and not _derived(c.path or "", goal, existing):
                path = c.path or ""
                issues.append(
                    PolicyIssue(m.id, f"conditions[{i}]", path, UNDERIVED_RULE, UNDERIVED_HINT)
                )
        if m.check:
            hit = _command_issue(m.check, goal, existing, names, goal_idents, suffix)
            if hit is not None:
                issues.append(PolicyIssue(m.id, "check", m.check, hit[0], hit[1]))
        for i, c in enumerate(m.conditions):
            if c.kind != "command":
                continue
            command = c.cmd or ""
            hit = _command_issue(command, goal, existing, names, goal_idents, suffix)
            if hit is not None:
                issues.append(PolicyIssue(m.id, f"conditions[{i}]", command, hit[0], hit[1]))
    return issues


def drop_policy_issues(
    plan: ProjectPlan, issues: list[PolicyIssue]
) -> tuple[ProjectPlan, list[str]]:
    milestones = []
    for m in plan.milestones:
        fields = {i.field for i in issues if i.milestone_id == m.id}
        check = None if "check" in fields else m.check
        conds = tuple(
            c for i, c in enumerate(m.conditions) if f"conditions[{i}]" not in fields
        )
        gated_before = m.check is not None or bool(m.conditions)
        ungated = gated_before and bool(fields) and check is None and not conds
        milestones.append(
            dataclasses.replace(m, check=check, conditions=conds, ungated=ungated)
        )
    new_plan = dataclasses.replace(plan, milestones=tuple(milestones))
    return new_plan, [m.id for m in new_plan.milestones if m.ungated]


def repair_messages(
    messages: list[Message], reply: str, error: str, *, hint: str | None = None
) -> list[Message]:
    return [
        *messages,
        Message("assistant", reply[:4000]),
        Message(
            "user",
            f"Your reply was invalid: {error}\n"
            + (hint + "\n" if hint else "")
            + "Reply again with only the corrected JSON object.",
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


def _scan_objects(s: str) -> Any | None:
    body = _strip_fence_lines(s)
    starts = [i for i, c in enumerate(body) if c == "{"][:64]
    for b in starts:
        e = _block_end(body, b, '"')
        if e == -1:
            continue
        for cand in (body[b:e], _drop_trailing_commas(body[b:e])):
            try:
                data = json.loads(cand)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "milestones" in data:
                return data
    return None


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
    scanned = _scan_objects(text.strip())
    if scanned is not None:
        return scanned, ("scan_objects",)
    return None


def classify_reply(text: str, error: str, finish_reason: str | None = None) -> str:
    if not text.strip():
        return "empty"
    if finish_reason == "length":
        return "truncated"
    if not error.startswith("model reply is not valid JSON"):
        return "schema"
    body = _strip_fence_lines(text.strip())
    b = body.find("{")
    if b == -1:
        return "no_object"
    e = _block_end(body, b, '"')
    if e == -1:
        return "truncated"
    if body[:b].strip() or body[e:].strip():
        return "prose_or_fence"
    return "other"


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
    if isinstance(raw, list):
        for i, item in enumerate(raw, 1):
            if isinstance(item, dict) and "ungated" in item:
                raise PlanError(f"model reply: milestone {i}: unknown key 'ungated'")
    return parse_plan(data, "from model reply")


async def plan_project(
    goal: str,
    call: Callable[[list[Message]], Awaitable[str]],
    *,
    max_milestones: int = 8,
    lenient: bool = False,
    policy: PlanPolicy | None = None,
    policy_repairs: int = 1,
    on_policy: Callable[[dict], None] | None = None,
    on_reject: Callable[[dict], None] | None = None,
    repair_hint: bool = False,
    workspace_files: Sequence[str] | None = None,
    workspace_tests: Sequence[str] = (),
) -> ProjectPlan:
    extra: dict[str, Any] = {} if workspace_files is None else {"workspace_files": workspace_files}
    if policy is None:
        msgs = plan_messages(goal, max_milestones, **extra)
    else:
        msgs = plan_messages(goal, max_milestones, policy_rules=policy.rules_text(), **extra)
    n = 1
    reply = await call(msgs)
    try:
        plan = plan_from_text(reply, max_milestones=max_milestones, lenient=lenient)
        last_reply = reply
    except PlanError as e1:
        cause = classify_reply(reply, str(e1))
        if on_reject is not None:
            on_reject(
                {
                    "stage": "schema",
                    "call": n,
                    "error": str(e1),
                    "cause": cause,
                    "reply": reply,
                }
            )
        n += 1
        reply2 = await call(
            repair_messages(
                msgs,
                reply,
                str(e1),
                hint=REPAIR_HINTS.get(cause) if repair_hint else None,
            )
        )
        try:
            plan = plan_from_text(reply2, max_milestones=max_milestones, lenient=lenient)
            last_reply = reply2
        except PlanError as e2:
            if on_reject is not None:
                on_reject(
                    {
                        "stage": "schema_repair",
                        "call": n,
                        "error": str(e2),
                        "cause": classify_reply(reply2, str(e2)),
                        "reply": reply2,
                    }
                )
            raise PlanError(f"planner reply invalid after one repair attempt: {e2}") from e2
    if policy is None and workspace_files is None:
        return plan

    def validate(p: ProjectPlan) -> list[PolicyIssue]:
        found: list[PolicyIssue] = []
        if policy is not None:
            found += validate_plan_policy(p, policy)
        if workspace_files is not None:
            found += validate_plan_paths(p, goal, workspace_files, workspace_tests)
        seen: set[tuple[str, str]] = set()
        unique: list[PolicyIssue] = []
        for issue in found:
            key = (issue.milestone_id, issue.field)
            if key not in seen:
                seen.add(key)
                unique.append(issue)
        return unique

    issues = validate(plan)
    first = len(issues)
    path_first = sum(1 for i in issues if i.rule in PLAN_RULES)
    rounds = 0
    while issues and rounds < policy_repairs:
        rounds += 1
        if any(i.rule in PLAN_RULES for i in issues):
            repair = plan_repair_messages(msgs, last_reply, issues)
        else:
            repair = policy_repair_messages(msgs, last_reply, issues)
        r = await call(repair)
        n += 1
        try:
            cand = plan_from_text(r, max_milestones=max_milestones, lenient=lenient)
        except PlanError as e:
            if on_reject is not None:
                on_reject(
                    {
                        "stage": "policy_repair",
                        "call": n,
                        "error": str(e),
                        "cause": classify_reply(r, str(e)),
                        "reply": r,
                    }
                )
            break
        plan, last_reply = cand, r
        issues = validate(plan)
    plan, ungated = drop_policy_issues(plan, issues)
    if on_policy is not None:
        payload: dict = {
            "issues": first,
            "repaired": max(0, first - len(issues)),
            "dropped": len(issues),
            "rounds": rounds,
            "ungated": ungated,
            "policy_dropped": [i.dropped() for i in issues],
        }
        if workspace_files is not None:
            payload["path_issues"] = path_first
        on_policy(payload)
    return plan


async def generate_plan(
    goal: str,
    config: CoraConfig,
    governor: BudgetGovernor,
    *,
    meter: CostMeter,
    max_milestones: int,
    providers: ProviderPool | None = None,
    policy: PlanPolicy | None = None,
    on_event: Callable[[str, dict], None] | None = None,
    workspace: Path | None = None,
) -> tuple[ProjectPlan, dict]:
    spec = HeuristicRouter(config).model_for(config.router.default)
    provider = (providers or ProviderPool(config)).get(spec.provider)
    calls = 0
    captured: dict | None = None
    metas: list[tuple[str | None, int | None]] = []

    def on_policy(payload: dict) -> None:
        nonlocal captured
        captured = payload

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
        metas.append((resp.finish_reason, resp.output_tokens))
        return resp.text

    workspace_files = (
        workspace_listing(workspace)
        if config.project.goal_paths and workspace is not None
        else None
    )
    workspace_tests = (
        workspace_test_names(workspace, workspace_files)
        if workspace_files is not None and workspace is not None
        else ()
    )

    def on_reject(payload: dict) -> None:
        if on_event is None:
            return
        fr, tok = metas[payload["call"] - 1]
        names = secret_env_names(config)
        reply = scrub_secrets(payload["reply"], os.environ, names)
        on_event(
            "plan_reply_rejected",
            {
                "stage": payload["stage"],
                "call": payload["call"],
                "error": scrub_secrets(payload["error"], os.environ, names),
                "cause": classify_reply(payload["reply"], payload["error"], fr),
                "finish_reason": fr,
                "tokens_out": tok,
                "reply_chars": len(reply),
                "reply": reply[:PLAN_REJECT_MAX_CHARS],
                "reply_cut": len(reply) > PLAN_REJECT_MAX_CHARS,
            },
        )

    plan = await plan_project(
        goal,
        call,
        max_milestones=max_milestones,
        lenient=config.agent.lenient_parse,
        policy=policy,
        policy_repairs=config.project.policy_repairs,
        on_policy=on_policy,
        on_reject=on_reject,
        repair_hint=config.project.plan_repair_hint,
        workspace_files=workspace_files,
        workspace_tests=workspace_tests,
    )
    info = {
        "model": spec.id,
        "calls": calls,
        "cost_usd": meter.total_cost_usd,
        "tokens_in": sum(r.input_tokens for r in meter.records),
        "tokens_out": sum(r.output_tokens for r in meter.records),
        "policy": captured or None,
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
    plan_policy: dict | None = None,
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
        "plan_policy": plan_policy,
    }


def plan_outcome(
    path: Path,
    plan: ProjectPlan,
    meter: CostMeter,
    governor: BudgetGovernor | None,
    *,
    wall_s: float,
    warnings: Sequence[str] = (),
    plan_policy: dict | None = None,
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
        plan_policy=plan_policy,
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
