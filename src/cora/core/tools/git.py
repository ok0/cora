from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cora.core.tools.base import ToolContext, ToolResult, truncate_text

GIT_BASE = (
    "git", "--no-pager", "--literal-pathspecs", "-c", "core.fsmonitor=false",
    "-c", "core.quotepath=false", "-c", "color.ui=false", "-c", "core.pager=cat",
)
NOT_A_REPO = "error: the workspace is not inside a git repository; git tools need one"
NOTHING_STAGED = "error: nothing staged to commit; stage files with git_add first"
BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")
MAX_ADD_PATHS = 50
MAX_COMMIT_CHARS = 5000
MAX_PREVIEW_FILES = 50


def git_env(ctx: ToolContext) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ctx.hidden_env and (not k.startswith("GIT_") or k == "GIT_CEILING_DIRECTORIES")
    }
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_EDITOR="true",
        GIT_PAGER="cat",
        PAGER="cat",
        GIT_OPTIONAL_LOCKS="0",
        LC_ALL="C",
    )
    return env


async def run_git(
    ctx: ToolContext, args: Sequence[str], *, stdin: bytes | None = None
) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *GIT_BASE,
            *args,
            cwd=ctx.workspace.root,
            env=git_env(ctx),
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return 127, "error: git is not installed"
    timeout = ctx.limits.git_timeout_s
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"error: git timed out after {timeout}s"
    rc = -1 if proc.returncode is None else proc.returncode
    return rc, (out or b"").decode("utf-8", "replace")


def run_git_sync(ctx: ToolContext, args: Sequence[str]) -> tuple[int, str]:
    timeout = ctx.limits.git_timeout_s
    try:
        proc = subprocess.run(
            [*GIT_BASE, *args],
            cwd=ctx.workspace.root,
            env=git_env(ctx),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "error: git is not installed"
    except subprocess.TimeoutExpired:
        return -1, f"error: git timed out after {timeout}s"
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


async def repo_error(ctx: ToolContext) -> ToolResult | None:
    rc, out = await run_git(ctx, ["rev-parse", "--is-inside-work-tree"])
    if rc == 0 and out.strip() == "true":
        return None
    return ToolResult(False, NOT_A_REPO)


def check_args(args: dict[str, Any], allowed: set[str]) -> None:
    extra = set(args) - allowed
    if extra:
        raise ValueError(
            f"unsupported argument(s): {sorted(extra)}; allowed: {sorted(allowed)}"
        )


def safe_path(ctx: ToolContext, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty string")
    if "\0" in value:
        raise ValueError("path must not contain NUL bytes")
    if value.startswith("-"):
        raise ValueError(f"path must not start with '-': {value}")
    if Path(value).is_absolute() or value.startswith("~"):
        raise ValueError("use a path relative to the workspace")
    ctx.workspace.resolve(value)
    return os.path.normpath(value)


def validate_branch(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not BRANCH_RE.fullmatch(name)
        or any(bad in name for bad in ("..", "//", "@{"))
        or name.endswith(("/", ".", ".lock"))
        or any(part.startswith(".") for part in name.split("/"))
        or name == "HEAD"
    ):
        raise ValueError(f"invalid branch name: {name!r}")
    return name


class GitStatusTool:
    name = "git_status"
    description = "Show git status: branch and changed files."
    terse_description = "Show git status."
    args_doc = "{}"
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    requires_approval = False
    read_only = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, set())

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        rc, out = await run_git(
            ctx, ["status", "--short", "--branch", "--untracked-files=normal"]
        )
        return ToolResult(rc == 0, truncate_text(out or "clean", ctx.limits.git_max_output_chars))


class GitDiffTool:
    name = "git_diff"
    description = "Show git diff of unstaged changes, or staged changes with staged=true."
    terse_description = "Show git diff (staged=true: staged changes)."
    args_doc = '{"staged": bool = false, "path": str | None}'
    parameters = {
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "description": "show staged changes (default false)"},
            "path": {
                "type": ["string", "null"],
                "description": "limit the diff to this workspace-relative path",
            },
        },
        "required": [],
        "additionalProperties": False,
    }
    requires_approval = False
    read_only = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, {"staged", "path"})
        if "staged" in args and not isinstance(args["staged"], bool):
            raise ValueError("'staged' must be true or false")
        if args.get("path") is not None:
            safe_path(ctx, args["path"])

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        cmd = ["diff", "--no-color", "--no-ext-diff", "--no-textconv"]
        if args.get("staged", False):
            cmd.append("--cached")
        cmd.append("--")
        if args.get("path") is not None:
            cmd.append(safe_path(ctx, args["path"]))
        rc, out = await run_git(ctx, cmd)
        text = truncate_text(out or "no changes", ctx.limits.git_max_output_chars)
        return ToolResult(rc == 0, text)


class GitLogTool:
    name = "git_log"
    description = "Show recent commits, newest first."
    terse_description = "Show recent commits."
    args_doc = '{"count": int = 10, "path": str | None}'
    parameters = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "number of commits (default 10)"},
            "path": {
                "type": ["string", "null"],
                "description": "limit the log to this workspace-relative path",
            },
        },
        "required": [],
        "additionalProperties": False,
    }
    requires_approval = False
    read_only = True

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, {"count", "path"})
        if "count" in args and (
            isinstance(args["count"], bool) or not isinstance(args["count"], int)
        ):
            raise ValueError("'count' must be an integer")
        if args.get("path") is not None:
            safe_path(ctx, args["path"])

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        n = max(1, min(args.get("count", 10), ctx.limits.git_log_max_count))
        cmd = ["log", f"-n{n}", "--no-color", "--date=short", "--format=%h %ad %an: %s", "--"]
        if args.get("path") is not None:
            cmd.append(safe_path(ctx, args["path"]))
        rc, out = await run_git(ctx, cmd)
        return ToolResult(rc == 0, truncate_text(out, ctx.limits.git_max_output_chars))


class GitAddTool:
    name = "git_add"
    description = "Stage files for commit (needs approval)."
    terse_description = "Stage files (needs approval)."
    args_doc = '{"paths": [str]}'
    parameters = {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_ADD_PATHS,
            }
        },
        "required": ["paths"],
        "additionalProperties": False,
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, {"paths"})
        paths = args.get("paths")
        if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_ADD_PATHS:
            raise ValueError(f"'paths' must be a non-empty list of up to {MAX_ADD_PATHS} paths")
        for p in paths:
            safe_path(ctx, p)

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rels = [safe_path(ctx, p) for p in args["paths"]]
        return ToolResult(True, "$ git add -- " + " ".join(shlex.quote(p) for p in rels))

    def approval_key(self, args: dict[str, Any]) -> str:
        return "git_add"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        rels = [safe_path(ctx, p) for p in args["paths"]]
        rc, out = await run_git(ctx, ["add", "--", *rels])
        if rc != 0:
            return ToolResult(False, truncate_text(out, ctx.limits.git_max_output_chars))
        return ToolResult(True, f"ok: staged {len(rels)} path(s)")


class GitCommitTool:
    name = "git_commit"
    description = "Commit staged changes with a message (needs approval)."
    terse_description = "Commit staged changes (needs approval)."
    args_doc = '{"message": str}'
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "commit message"},
        },
        "required": ["message"],
        "additionalProperties": False,
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, {"message"})
        message = args.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("commit message must not be empty")
        if len(message) > MAX_COMMIT_CHARS:
            raise ValueError(f"commit message must be at most {MAX_COMMIT_CHARS} characters")

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rc, out = run_git_sync(ctx, ["rev-parse", "--is-inside-work-tree"])
        if rc != 0 or out.strip() != "true":
            return ToolResult(False, NOT_A_REPO)
        rc, names = run_git_sync(ctx, ["diff", "--cached", "--name-status"])
        if rc != 0:
            return ToolResult(False, truncate_text(names, ctx.limits.git_max_output_chars))
        if not names.strip():
            return ToolResult(False, NOTHING_STAGED)
        listing = "\n".join(names.splitlines()[:MAX_PREVIEW_FILES])
        return ToolResult(
            True, f"Commit message:\n{args['message']}\n\nStaged files:\n{listing}"
        )

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        rc, _ = await run_git(ctx, ["diff", "--cached", "--quiet"])
        if rc == 0:
            return ToolResult(False, NOTHING_STAGED)
        rc, out = await run_git(
            ctx, ["commit", "--file=-"], stdin=args["message"].encode("utf-8")
        )
        if rc != 0:
            return ToolResult(False, truncate_text(out, ctx.limits.git_max_output_chars))
        _, head = await run_git(ctx, ["log", "-1", "--format=%h %s"])
        return ToolResult(True, f"ok: committed {head.strip()}")


class GitBranchTool:
    name = "git_branch"
    description = "Switch to a local branch, or create it with create=true (needs approval)."
    terse_description = "Switch or create a branch (needs approval)."
    args_doc = '{"name": str, "create": bool = false}'
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "local branch name"},
            "create": {"type": "boolean", "description": "create the branch (default false)"},
        },
        "required": ["name"],
        "additionalProperties": False,
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        check_args(args, {"name", "create"})
        validate_branch(args.get("name"))
        if "create" in args and not isinstance(args["create"], bool):
            raise ValueError("'create' must be true or false")

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        create = args.get("create", False)
        return ToolResult(True, f"$ git switch {'-c ' if create else ''}{args['name']}")

    def approval_key(self, args: dict[str, Any]) -> str:
        return "git_branch"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        err = await repo_error(ctx)
        if err is not None:
            return err
        name = args["name"]
        create = args.get("create", False)
        cmd = ["switch", "-c", name] if create else ["switch", "--no-guess", name]
        rc, out = await run_git(ctx, cmd)
        if rc != 0:
            return ToolResult(False, truncate_text(out, ctx.limits.git_max_output_chars))
        verb = "created and switched to" if create else "switched to"
        return ToolResult(True, f"ok: {verb} {name}")
