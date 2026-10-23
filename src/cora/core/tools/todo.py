from __future__ import annotations

from typing import Any

from cora.core.tools.base import TODO_STATUSES, TodoList, ToolContext, ToolResult


class TodoWriteTool:
    name = "todo_write"
    description = "Replace the whole TODO list for this task. At most one item in_progress."
    terse_description = "Replace the TODO list; at most one in_progress."
    args_doc = '{"todos": [{"content": str, "status": "pending"|"in_progress"|"completed"}]}'
    parameters = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": list(TODO_STATUSES)},
                    },
                    "required": ["content", "status"],
                },
            }
        },
        "required": ["todos"],
        "additionalProperties": False,
    }
    requires_approval = False
    read_only = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        extra = set(args) - {"todos"}
        if extra:
            raise ValueError(f"unsupported argument(s): {sorted(extra)}")
        TodoList.parse(args["todos"])

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ctx.todos.replace(TodoList.parse(args["todos"]))
        return ToolResult(True, "TODO list updated:\n" + ctx.todos.render())
