from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from cora.core.config import DelegationSettings
from cora.core.memory import compress_observations, read_path_of, superseded
from cora.core.react import parse_step
from cora.core.tools import ToolContext, ToolRegistry, ToolResult
from cora.core.types import Message

EXPLORE_TOOLS: tuple[str, ...] = (
    "list_files",
    "read_file",
    "search",
    "git_status",
    "git_diff",
    "git_log",
)
DELEGATE_MODES = ("explore", "general")
SUMMARY_TRUNCATED = " ...[summary truncated]"
DO_IT_YOURSELF = "do the subtask yourself with the other tools."


class SubagentBudgetExceeded(Exception):
    """raised by the call wrapper when the budget gate refuses a sub-agent call"""


def explore_registry(tools: ToolRegistry) -> ToolRegistry:
    return tools.subset(EXPLORE_TOOLS)


def clip_summary(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - len(SUMMARY_TRUNCATED)].rstrip() + SUMMARY_TRUNCATED


class DelegateTool:
    name = "delegate"
    terse_description = "Give a subtask to a sub-agent; returns its summary."
    description = (
        "Hand a narrow subtask to a sub-agent with a fresh context; you get back only its short "
        "summary."
    )
    args_doc = (
        '{"task": str, "mode": "explore" (read-only lookup; several in one response run in '
        'parallel) | "general" (default; may edit; runs alone)}'
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["explore", "general"],
                "description": (
                    "explore = read-only lookup, runs in parallel; "
                    "general (default) = may edit, runs alone"
                ),
            },
        },
        "required": ["task"],
    }
    requires_approval = False
    read_only = False
    plan_safe = True

    def __init__(
        self,
        runner: Callable[[str, str], Awaitable[ToolResult]],
        *,
        parallel_explore: bool = False,
    ) -> None:
        self._runner = runner
        self._parallel_explore = parallel_explore

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        if not isinstance(args.get("task"), str) or not args["task"].strip():
            raise ValueError("'task' must be a non-empty string")
        if (args.get("mode") or "general") not in DELEGATE_MODES:
            raise ValueError("'mode' must be 'explore' or 'general'")

    def parallel_safe_for(self, args: Any) -> bool:
        return self._parallel_explore and isinstance(args, dict) and args.get("mode") == "explore"

    def plan_safe_for(self, args: Any) -> bool:
        return isinstance(args, dict) and args.get("mode") == "explore"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await self._runner(args["task"].strip(), args.get("mode") or "general")


@dataclass(frozen=True)
class SubResult:
    ok: bool
    answer: str | None
    reason: str
    steps: int


async def run_subagent(
    task: str,
    *,
    call: Callable[[list[Message]], Awaitable[str]],
    tools: ToolRegistry,
    ctx: ToolContext,
    system_prompt: str,
    settings: DelegationSettings,
    tokens_used: Callable[[], int],
    cost_exceeded: Callable[[], bool],
    on_tool: Callable[[str, Any, ToolResult], None],
    max_observation_chars: int,
    dedupe_reads: bool = False,
    compress_chars: int = 0,
    keep_last: int = 8,
) -> SubResult:
    messages = [Message("system", system_prompt), Message("user", f"Task: {task}")]
    reads: dict[str, int] = {}
    steps = 0
    try:
        async with asyncio.timeout(settings.timeout_s):
            while steps < settings.max_steps:
                if cost_exceeded():
                    return SubResult(False, None, "cost_limit", steps)
                if compress_chars > 0:
                    compress_observations(
                        messages,
                        compress_chars,
                        keep_last,
                        start=2,
                        protected=set(reads.values()),
                    )
                text = await call(messages)
                steps += 1
                if tokens_used() > settings.max_tokens:
                    return SubResult(False, None, "token_budget", steps)
                step = parse_step(text)
                messages.append(Message("assistant", text.split("\nObservation:")[0].strip()))
                if step.final_answer is not None:
                    return SubResult(True, step.final_answer, "ok", steps)
                if step.error:
                    messages.append(Message("user", f"Observation: {step.error}"))
                    continue
                res = await tools.execute(step.action or "", step.action_input, ctx)
                on_tool(step.action or "", step.action_input, res)
                observed = res.output[:max_observation_chars]
                if dedupe_reads or compress_chars > 0:
                    p = read_path_of(
                        ctx.workspace.root, step.action or "", step.action_input, res.ok
                    )
                    if p is not None:
                        if dedupe_reads and p in reads:
                            i = reads[p]
                            messages[i] = replace(messages[i], content=superseded(p))
                        reads[p] = len(messages)
                messages.append(Message("user", f"Observation: {observed}"))
    except TimeoutError:
        return SubResult(False, None, "timeout", steps)
    except SubagentBudgetExceeded:
        return SubResult(False, None, "cost_limit", steps)
    except Exception as e:
        return SubResult(False, None, f"error: {type(e).__name__}: {e}"[:200], steps)
    return SubResult(False, None, "max_steps", steps)
