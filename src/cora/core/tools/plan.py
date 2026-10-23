from __future__ import annotations

from typing import Any

from cora.core.tools.base import ToolContext, ToolResult

MAX_PLAN_CHARS = 8000


class SubmitPlanTool:
    name = "submit_plan"
    description = "Plan mode: submit your final step-by-step plan for user approval."
    terse_description = "Submit the final plan for approval."
    args_doc = '{"plan": str}'
    parameters = {
        "type": "object",
        "properties": {"plan": {"type": "string"}},
        "required": ["plan"],
        "additionalProperties": False,
    }
    requires_approval = False
    read_only = False
    plan_safe = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        extra = set(args) - {"plan"}
        if extra:
            raise ValueError(f"unsupported argument(s): {sorted(extra)}")
        plan = args["plan"]
        if not isinstance(plan, str) or not plan.strip():
            raise ValueError("'plan' must be a non-empty string")

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ctx.submitted_plan = args["plan"].strip()[:MAX_PLAN_CHARS]
        return ToolResult(
            True, "plan submitted for user review; now reply with a one-line final answer"
        )
