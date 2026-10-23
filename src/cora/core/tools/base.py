from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cora.core.config import ToolSettings
from cora.core.errors import WorkspaceViolation

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".cora",
        ".venv",
        "node_modules",
        "__pycache__",
        ".reference",
        ".request",
        ".pytest_cache",
        ".ruff_cache",
    }
)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    summary: str
    detail: str = ""
    always_key: str = ""


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def resolve(self, rel: str) -> Path:
        p = (self.root / Path(rel).expanduser()).resolve()
        if not p.is_relative_to(self.root):
            raise WorkspaceViolation(f"path outside workspace: {rel}")
        return p


class ApprovalPolicy:
    def __init__(self, mode: str = "ask", ask: Callable[[str], bool] | None = None,
                 review: Callable[[ApprovalRequest], str] | None = None) -> None:
        self.mode = mode
        self.ask = ask
        self.review = review
        self.always_allowed: set[str] = set()
        self.denied = 0

    def approve(self, action: str, request: ApprovalRequest | None = None) -> bool:
        if self.mode == "auto":
            return True
        if self.mode in ("deny", "policy"):
            self.denied += 1
            return False
        if request is not None and request.always_key in self.always_allowed:
            return True
        if self.review is not None and request is not None:
            answer = self.review(request)
            if answer == "always":
                self.always_allowed.add(request.always_key)
                return True
            if answer == "yes":
                return True
            self.denied += 1
            return False
        if self.ask:
            if bool(self.ask(action)):
                return True
        self.denied += 1
        return False


TODO_STATUSES = ("pending", "in_progress", "completed")
TODO_MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
MAX_TODOS = 20
MAX_TODO_CHARS = 150


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: str


class TodoList:
    def __init__(self) -> None:
        self.items: list[TodoItem] = []

    @staticmethod
    def parse(raw: Any) -> list[TodoItem]:
        if not isinstance(raw, list):
            raise ValueError("'todos' must be a list")
        if len(raw) > MAX_TODOS:
            raise ValueError(f"at most {MAX_TODOS} items")
        items: list[TodoItem] = []
        for i, entry in enumerate(raw, 1):
            if not isinstance(entry, dict) or set(entry) - {"content", "status"}:
                raise ValueError(f"item {i}: must be an object with 'content' and 'status'")
            content = entry.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"item {i}: 'content' must be a non-empty string")
            if len(content) > MAX_TODO_CHARS:
                raise ValueError(f"item {i}: 'content' is longer than {MAX_TODO_CHARS} chars")
            status = entry.get("status")
            if status not in TODO_STATUSES:
                raise ValueError(f"item {i}: 'status' must be one of {list(TODO_STATUSES)}")
            items.append(TodoItem(content.strip(), status))
        if sum(1 for t in items if t.status == "in_progress") > 1:
            raise ValueError("at most one item may be in_progress")
        return items

    def replace(self, items: list[TodoItem]) -> None:
        self.items = list(items)

    def clear(self) -> None:
        self.items = []

    def render(self) -> str:
        if not self.items:
            return "No TODO items."
        return "\n".join(f"{TODO_MARKS[t.status]} {t.content}" for t in self.items)


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated: {len(text) - limit} more chars]"


@dataclass
class ToolContext:
    workspace: Workspace
    approval: ApprovalPolicy
    shell_timeout_s: int = 60
    originals: dict[str, str | None] = field(default_factory=dict)
    hidden_env: frozenset[str] = frozenset()
    limits: ToolSettings = field(default_factory=ToolSettings)
    todos: TodoList = field(default_factory=TodoList)
    plan_mode: bool = False
    submitted_plan: str | None = None
    http_transport: Any = None
    resolver: Callable[[str, int], Awaitable[list[str]]] | None = None
    disabled_groups: frozenset[str] = frozenset()
    hidden_groups: set[str] = field(default_factory=set)
    forced_groups: frozenset[str] = frozenset()
    gate: Any = None
    budget: Any = None
    located_errors: bool = False
    raw_file_body: bool = False


class Tool(Protocol):
    name: str
    description: str
    args_doc: str
    requires_approval: bool

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None: ...

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...
