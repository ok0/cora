from __future__ import annotations

import asyncio
import json
from collections.abc import Collection, Sequence
from typing import Any

from cora.core.errors import WorkspaceViolation
from cora.core.policy import approval_mode_of
from cora.core.toolgroups import group_of
from cora.core.tools.base import ApprovalRequest, Tool, ToolContext, ToolResult

FALLBACK_PARAMETERS = {"type": "object", "properties": {}, "additionalProperties": True}
PLAN_MODE_DENIED = (
    "denied: plan mode is on, so '{name}' was not run (only read-only tools run in plan mode)"
)
GROUP_DISABLED = (
    "error: '{name}' was not run: it belongs to the tool group '{group}', "
    "which is disabled. Enable it with `/tools {group} on`; until then use the other tools."
)
GROUP_AUTO_ENABLED = (
    "note: '{name}' belongs to the tool group '{group}', which was not "
    "loaded for this request; the group is now enabled for this session.\n"
)
BUDGET_STOPPED = "not executed: the {cap} budget cap is reached; the run stops"
TERSE_MAX_CHARS = 60


def _clip(text: str, limit: int = TERSE_MAX_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def terse_text(t: Tool) -> str:
    return _clip(
        getattr(t, "terse_description", None)
        or getattr(t, "native_description", None)
        or t.description
    )


def allowed_in_plan_mode(tool: Tool, args: Any = None) -> bool:
    check = getattr(tool, "plan_safe_for", None)
    if check is not None and args is not None:
        return bool(check(args))
    if getattr(tool, "plan_safe", False):
        return True
    return bool(getattr(tool, "read_only", False)) and not tool.requires_approval


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools: dict[str, Tool] = {t.name: t for t in tools}

    def names(self) -> list[str]:
        return list(self._tools)

    def is_parallel_safe(self, name: str) -> bool:
        tool = self._tools.get(name)
        return (
            tool is not None
            and bool(getattr(tool, "read_only", False))
            and not tool.requires_approval
        )

    def is_parallel_call(self, name: str, args: Any) -> bool:
        tool = self._tools.get(name)
        if tool is None:
            return False
        check = getattr(tool, "parallel_safe_for", None)
        return bool(check(args)) if check is not None else self.is_parallel_safe(name)

    def extended(self, extra: Sequence[Tool]) -> ToolRegistry:
        return ToolRegistry([*self._tools.values(), *extra])

    def subset(self, names: Collection[str]) -> ToolRegistry:
        return ToolRegistry([t for t in self._tools.values() if t.name in names])

    async def _execute_isolated(self, name: str, args: Any, ctx: ToolContext) -> ToolResult:
        try:
            return await self.execute(name, args, ctx)
        except Exception as e:
            return ToolResult(False, f"error: {type(e).__name__}: {e}")

    async def execute_many(
        self, calls: Sequence[tuple[str, Any]], ctx: ToolContext, max_concurrency: int
    ) -> list[ToolResult]:
        results: list[ToolResult | None] = [None] * len(calls)
        sem = asyncio.Semaphore(max(1, max_concurrency))

        async def run_one(k: int) -> None:
            async with sem:
                results[k] = await self._execute_isolated(calls[k][0], calls[k][1], ctx)

        i = 0
        while i < len(calls):
            if not self.is_parallel_call(calls[i][0], calls[i][1]):
                results[i] = await self._execute_isolated(calls[i][0], calls[i][1], ctx)
                i += 1
                continue
            j = i
            while j < len(calls) and self.is_parallel_call(calls[j][0], calls[j][1]):
                j += 1
            async with asyncio.TaskGroup() as tg:
                for k in range(i, j):
                    tg.create_task(run_one(k))
            i = j
        return [r if r is not None else ToolResult(False, "error: not executed") for r in results]

    def describe(
        self,
        exclude: Collection[str] = frozenset(),
        *,
        terse: bool = False,
        raw_blocks: bool = False,
    ) -> str:
        def doc(t: Tool) -> str:
            return (getattr(t, "raw_args_doc", None) if raw_blocks else None) or t.args_doc

        if terse:
            return "\n".join(
                f"- {t.name}: {terse_text(t)} Args: {doc(t)}"
                for t in self._tools.values()
                if t.name not in exclude
            )
        return "\n".join(
            f"- {t.name}: {t.description} Args: {doc(t)}"
            for t in self._tools.values()
            if t.name not in exclude
        )

    def schemas(self, exclude: Collection[str] = frozenset(), *, terse: bool = False) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": terse_text(t) if terse
                    else getattr(t, "native_description", None)
                    or f"{t.description} Args: {t.args_doc}",
                    "parameters": getattr(t, "parameters", None) or FALLBACK_PARAMETERS,
                },
            }
            for t in self._tools.values()
            if t.name not in exclude
        ]

    async def execute(self, name: str, args: Any, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, f"unknown tool '{name}'. available: {self.names()}")
        group = group_of(name)
        if group not in (None, "core"):
            if group in ctx.disabled_groups:
                return ToolResult(False, GROUP_DISABLED.format(name=name, group=group))
            if group in ctx.hidden_groups:
                ctx.hidden_groups.discard(group)
                res = await self._execute_tool(tool, name, args, ctx)
                note = GROUP_AUTO_ENABLED.format(name=name, group=group)
                return ToolResult(res.ok, note + res.output)
        return await self._execute_tool(tool, name, args, ctx)

    async def _execute_tool(
        self, tool: Tool, name: str, args: Any, ctx: ToolContext
    ) -> ToolResult:
        budget = ctx.budget
        if budget is not None:
            cap = budget.check_tool_call()
            if cap is not None:
                return ToolResult(False, BUDGET_STOPPED.format(cap=cap))
            budget.add_tool_calls(1, name=name)
        if ctx.plan_mode and not allowed_in_plan_mode(tool, args):
            return ToolResult(False, PLAN_MODE_DENIED.format(name=name))
        if not isinstance(args, dict):
            return ToolResult(False, "Action Input must be a JSON object")
        try:
            verdict = (ctx.gate.check(name, args, approval_mode_of(ctx.approval))
                       if ctx.gate is not None else None)
            if verdict is not None and verdict.blocked:
                return ToolResult(False, verdict.message)
            tool.preflight(args, ctx)
            if tool.requires_approval and not (verdict is not None and verdict.final):
                detail = ""
                preview = getattr(tool, "preview", None)
                if preview is not None:
                    p = preview(args, ctx)
                    if not p.ok:
                        return p
                    detail = p.output
                key_fn = getattr(tool, "approval_key", None)
                summary = f"{name}: {json.dumps(args, ensure_ascii=False)[:500]}"
                request = ApprovalRequest(name, summary, detail, key_fn(args) if key_fn else name)
                if not ctx.approval.approve(summary, request):
                    return ToolResult(False, f"denied by user: approval required for {name}")
            return await tool.run(args, ctx)
        except WorkspaceViolation as e:
            return ToolResult(False, f"denied: {e}")
        except (KeyError, TypeError, ValueError) as e:
            return ToolResult(False, f"invalid arguments: {e}")
        except OSError as e:
            return ToolResult(False, f"error: {e}")
