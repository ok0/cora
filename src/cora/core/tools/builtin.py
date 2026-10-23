from __future__ import annotations

import asyncio
import difflib
import os
import re
import shlex
from pathlib import Path
from typing import Any

from cora.core import shellguard
from cora.core.errors import WorkspaceViolation
from cora.core.policy import approval_mode_of
from cora.core.tools.base import IGNORED_DIRS, ToolContext, ToolResult
from cora.core.tools.git import (
    GitAddTool,
    GitBranchTool,
    GitCommitTool,
    GitDiffTool,
    GitLogTool,
    GitStatusTool,
)
from cora.core.tools.todo import TodoWriteTool
from cora.core.tools.web import WebFetchTool

MAX_DIFF_CHARS = 8000
OLD_NOT_FOUND_PREFIX = "edit_file failed: 'old' text not found in "
RAW_MARKER_FIRST = frozenset({"<<<CONTENT", "<<<NEW"})
RAW_MARKER_LAST = frozenset({"CONTENT>>>", "NEW>>>", ">>>"})
NEAR_WINDOW = 160
SIMILAR_CUTOFF = 0.6


def unified_diff(rel: str, before: str, after: str) -> str:
    def norm(s: str) -> list[str]:
        return [ln if ln.endswith("\n") else ln + "\n" for ln in s.splitlines(keepends=True)]

    text = "".join(difflib.unified_diff(norm(before), norm(after), f"a/{rel}", f"b/{rel}"))
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + "\n... (diff truncated)\n"
    return text


def _real(dirpath: str, name: str) -> Path:
    return Path(os.path.realpath(os.path.join(dirpath, name)))


def _walk_guard(ctx: ToolContext) -> shellguard.PathGuard:
    return shellguard.PathGuard(ctx.workspace.root, shellguard.default_protected())


def _raw_marker_refusal(tool: str, field: str, text: str) -> ToolResult | None:
    lines = [ln.strip() for ln in text.strip().split("\n")]
    if lines[0] not in RAW_MARKER_FIRST and lines[-1] not in RAW_MARKER_LAST:
        return None
    label = "NEW" if field == "new" else "CONTENT"
    return ToolResult(
        False,
        f"{tool} failed: '{field}' starts or ends with a raw marker line, which was written "
        "inside the JSON string. Put the text after the closing } of Action Input, between a "
        f"line <<<{label} and a line {label}>>>, and do not also give '{field}' in the JSON.",
    )


def _write_finding(ctx: ToolContext, path: Path) -> str | None:
    gate = ctx.gate
    guard = gate.guard if gate is not None and hasattr(gate, "guard") else _walk_guard(ctx)
    f = guard.check_real(Path(os.path.realpath(path)), write=True)
    return None if f is None else f.reason


def _window(line: str, start: int) -> str:
    part = line[start : start + NEAR_WINDOW]
    pre = "…" if start > 0 else ""
    post = "…" if len(line) > start + NEAR_WINDOW else ""
    return pre + part + post


def locate_mismatch(text: str, old: str, shown: str) -> str:
    file_lines = text.split("\n")
    old_lines = old.split("\n")
    k0 = next((k for k, ln in enumerate(old_lines) if ln.strip()), None)
    if k0 is None:
        return f" No line in {shown} is similar to 'old' (it holds only whitespace)."
    target = old_lines[k0]
    best = -1.0
    cands: list[int] = []
    for i, ln in enumerate(file_lines):
        sm = difflib.SequenceMatcher(None, target, ln, autojunk=False)
        if sm.real_quick_ratio() < best or sm.quick_ratio() < best:
            continue
        r = sm.ratio()
        if r > best:
            best = r
            cands = [i]
        elif r == best:
            cands.append(i)
    if best < SIMILAR_CUTOFF:
        return (
            f" No line in {shown} is similar to the first non-empty line of 'old' "
            f"({_window(target, 0)}). Re-read the file with read_file."
        )
    best_i = cands[0]
    best_run = -1
    for i in cands:
        start = i - k0
        run = 0
        while run < len(old_lines):
            fi = start + run
            if fi < 0 or fi >= len(file_lines) or file_lines[fi] != old_lines[run]:
                break
            run += 1
        if run > best_run:
            best_run = run
            best_i = i
    k = best_run
    fi = best_i - k0 + k
    if fi >= len(file_lines):
        return (
            f" Nearest match: the first non-empty line of 'old' is closest to line {best_i + 1} "
            f"of {shown}; 'old' matches up to the end of the file and continues past it."
        )
    if fi < 0:
        fi = 0
    a, b = old_lines[k], file_lines[fi]
    n = min(len(a), len(b))
    p = 0
    while p < n and a[p] == b[p]:
        p += 1
    col = p + 1
    ws = max(0, col - 1 - 80)
    ctx = "\n".join(
        f"{m + 1:>6}| {_window(file_lines[m], ws)}"
        for m in range(max(0, fi - 1), min(len(file_lines), fi + 2))
    )
    return (
        f" Nearest match: the first non-empty line of 'old' is closest to line {best_i + 1} "
        f"of {shown}; the first difference is at line {fi + 1}, column {col}.\n"
        f"File lines around it:\n{ctx}\n'old' has there: {_window(a, ws)}"
    )


class ListFilesTool:
    name = "list_files"
    description = "List files recursively (relative paths)."
    terse_description = "List files recursively."
    args_doc = '{"path": str = "."}'
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "directory relative to the workspace (default '.')",
            }
        },
        "required": [],
    }
    requires_approval = False
    read_only = True
    MAX_ENTRIES = 200

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(self._list, args, ctx)

    def _list(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        base = ctx.workspace.resolve(args.get("path", "."))
        out: list[str] = []
        guard = _walk_guard(ctx)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS
                                 and guard.check_real(_real(dirpath, d), write=False) is None)
            for fn in sorted(filenames):
                if guard.check_real(_real(dirpath, fn), write=False) is not None:
                    continue
                if len(out) >= self.MAX_ENTRIES:
                    out.append("... (more)")
                    return ToolResult(True, "\n".join(out))
                rel = (Path(dirpath) / fn).relative_to(ctx.workspace.root)
                out.append(str(rel))
        return ToolResult(True, "\n".join(out))


class ReadFileTool:
    name = "read_file"
    description = "Read a text file with line numbers."
    terse_description = "Read a file with line numbers."
    args_doc = '{"path": str, "start_line": int = 1, "end_line": int | None}'
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "description": "1-based first line (default 1)"},
            "end_line": {"type": "integer", "description": "last line (default: end of file)"},
        },
        "required": ["path"],
    }
    requires_approval = False
    read_only = True
    MAX_LINES = 400

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        finding = _walk_guard(ctx).check_real(ctx.workspace.resolve(args["path"]), write=False)
        if finding is not None:
            raise WorkspaceViolation(finding.reason)

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(self._read, args, ctx)

    def _read(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        path = ctx.workspace.resolve(args["path"])
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(int(args.get("start_line", 1)), 1)
        end_arg = args.get("end_line")
        end = len(lines) if end_arg is None else min(int(end_arg), len(lines))
        chunk_end = min(end, start - 1 + self.MAX_LINES)
        out = [f"{n:>5}| {lines[n - 1]}" for n in range(start, chunk_end + 1)]
        if chunk_end < end:
            out.append(f"... (truncated; continue with start_line={chunk_end + 1})")
        return ToolResult(True, "\n".join(out))


class SearchTool:
    name = "search"
    description = "Search file contents with a regex; returns path:line: text."
    terse_description = "Regex search in files; returns path:line: text."
    args_doc = '{"pattern": str (regex), "path": str = ".", "max_results": int = 100}'
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Python regex"},
            "path": {"type": "string", "description": "directory (default '.')"},
            "max_results": {"type": "integer", "description": "default 100"},
        },
        "required": ["pattern"],
    }
    requires_approval = False
    read_only = True
    MAX_FILE_BYTES = 1_000_000

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        return None

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return await asyncio.to_thread(self._search, args, ctx)

    def _search(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            rx = re.compile(args["pattern"])
        except re.error as e:
            return ToolResult(False, f"invalid regex: {e}")
        base = ctx.workspace.resolve(args.get("path", "."))
        max_results = int(args.get("max_results", 100))
        hits: list[str] = []
        guard = _walk_guard(ctx)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS
                                 and guard.check_real(_real(dirpath, d), write=False) is None)
            for fn in sorted(filenames):
                fp = Path(dirpath) / fn
                if guard.check_real(_real(dirpath, fn), write=False) is not None:
                    continue
                try:
                    size = fp.stat().st_size
                except OSError:
                    continue
                if size > self.MAX_FILE_BYTES:
                    continue
                try:
                    text = fp.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                rel = fp.relative_to(ctx.workspace.root)
                for lineno, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                        if len(hits) >= max_results:
                            return ToolResult(True, "\n".join(hits))
        return ToolResult(True, "\n".join(hits) if hits else "no matches")


class EditFileTool:
    name = "edit_file"
    description = (
        "Replace one exact occurrence of 'old' with 'new' in a file. "
        "If old is empty and the file is missing or empty, creates the file with new."
    )
    terse_description = "Replace exact old with new; empty old creates the file."
    args_doc = '{"path": str, "old": str, "new": str}'
    raw_args_doc = (
        '{"path": str, "old": str, "new": str}, or put old/new verbatim (no JSON escaping): '
        'Action Input: {"path": str} then a line <<<OLD, the exact lines to replace, '
        "a line OLD>>>, a line <<<NEW, the new lines, a line NEW>>>"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {
                "type": "string",
                "description": "exact text to replace; empty to create a new file",
            },
            "new": {"type": "string"},
        },
        "required": ["path", "old", "new"],
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        ctx.workspace.resolve(args["path"])

    def _plan(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> tuple[Path, str, str | None, str] | ToolResult:
        shown = args["path"]
        path = ctx.workspace.resolve(shown)
        rel = path.relative_to(ctx.workspace.root).as_posix()
        old = args["old"]
        new = args["new"]
        if ctx.raw_file_body and isinstance(new, str):
            if (r := _raw_marker_refusal("edit_file", "new", new)) is not None:
                return r
        if path.is_dir():
            return ToolResult(False, f"edit_file failed: {shown} is a directory")
        if old == "":
            if not path.exists():
                return (path, rel, None, new)
            if path.stat().st_size == 0:
                return (path, rel, "", new)
            return ToolResult(
                False,
                f"edit_file failed: 'old' must be non-empty because {shown} already exists "
                "and is not empty. Copy the exact text to replace from read_file output. "
                "To replace the whole file, use write_file.",
            )
        if not path.exists():
            return ToolResult(
                False,
                f"edit_file failed: {shown} does not exist. To create a new file, "
                "use write_file with the full content.",
            )
        if old == new:
            return ToolResult(
                False, "edit_file failed: 'old' and 'new' are identical; nothing to change."
            )
        text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            msg = (
                f"{OLD_NOT_FOUND_PREFIX}{shown}. It must match the file exactly, including "
                "whitespace and indentation. Re-read the file with read_file and copy the exact "
                "lines without the line-number prefix."
            )
            if ctx.located_errors and _write_finding(ctx, path) is None:
                msg += locate_mismatch(text, old, shown)
            return ToolResult(False, msg)
        if count > 1:
            lines_found: list[int] = []
            start = 0
            while len(lines_found) < 10:
                idx = text.find(old, start)
                if idx == -1:
                    break
                lines_found.append(text.count("\n", 0, idx) + 1)
                start = idx + len(old)
            return ToolResult(
                False,
                f"edit_file failed: 'old' text occurs {count} times in {shown} "
                f"(lines {', '.join(map(str, lines_found))}). Include more surrounding lines "
                "so it matches exactly once.",
            )
        return (path, rel, text, text.replace(old, new, 1))

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        _, rel, before, after = p
        return ToolResult(True, unified_diff(rel, before or "", after))

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        path, rel, before, after = p
        ctx.originals.setdefault(rel, before)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
        return ToolResult(
            True, f"ok: created {args['path']}" if not before else f"ok: edited {args['path']}"
        )


class WriteFileTool:
    name = "write_file"
    description = (
        "Create or overwrite a file with content; append=true adds content to the end. "
        "Creates parent directories. Write a large file in parts: the first part, then "
        "append the rest."
    )
    terse_description = "Create/overwrite a file; append=true appends."
    args_doc = '{"path": str, "content": str, "append": bool = false}'
    raw_args_doc = (
        '{"path": str, "content": str, "append": bool = false}, or put content verbatim '
        '(no JSON escaping): Action Input: {"path": str, "append": bool = false} then a line '
        "<<<CONTENT, the file lines, a line CONTENT>>> (an empty line before CONTENT>>> ends "
        "the file with a newline)"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "append": {
                "type": "boolean",
                "description": "append instead of overwrite (default false)",
            },
        },
        "required": ["path", "content"],
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        p = ctx.workspace.resolve(args["path"])
        if (r := _write_finding(ctx, p)) is not None:
            raise WorkspaceViolation(r)

    def _plan(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> tuple[Path, str, str | None, str, bool] | ToolResult:
        shown = args["path"]
        path = ctx.workspace.resolve(shown)
        rel = path.relative_to(ctx.workspace.root).as_posix()
        if (r := _write_finding(ctx, path)) is not None:
            return ToolResult(False, f"write_file failed: {r}")
        content = args["content"]
        if not isinstance(content, str):
            return ToolResult(False, "write_file failed: 'content' must be a string")
        if ctx.raw_file_body and (r := _raw_marker_refusal("write_file", "content", content)):
            return r
        append = args.get("append", False)
        if not isinstance(append, bool):
            return ToolResult(False, "write_file failed: 'append' must be true or false")
        if path.is_dir():
            return ToolResult(False, f"write_file failed: {shown} is a directory")
        before = path.read_text(encoding="utf-8") if path.exists() else None
        after = (before or "") + content if append else content
        return (path, rel, before, after, append)

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        _, rel, before, after, _ = p
        return ToolResult(True, unified_diff(rel, before or "", after))

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        path, rel, before, after, append = p
        ctx.originals.setdefault(rel, before)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(after, encoding="utf-8")
        verb = "appended to" if append else ("overwrote" if before is not None else "created")
        lines = after.count("\n") + (1 if after and not after.endswith("\n") else 0)
        return ToolResult(
            True,
            f"ok: {verb} {args['path']} ({len(after.encode('utf-8'))} bytes, {lines} lines)",
        )


class DeleteFileTool:
    name = "delete_file"
    description = "Delete one regular file in the workspace (not a directory)."
    terse_description = "Delete one file."
    args_doc = '{"path": str}'
    parameters: dict = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    requires_approval = True
    read_only = False

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        p = ctx.workspace.resolve(args["path"])
        if (r := _write_finding(ctx, p)) is not None:
            raise WorkspaceViolation(r)

    def _plan(self, args: dict[str, Any], ctx: ToolContext) -> tuple[Path, str, str] | ToolResult:
        shown = args["path"]
        path = ctx.workspace.resolve(shown)
        rel = path.relative_to(ctx.workspace.root).as_posix()
        if (r := _write_finding(ctx, path)) is not None:
            return ToolResult(False, f"delete_file failed: {r}")
        if path.is_dir():
            return ToolResult(False, f"delete_file failed: {shown} is a directory")
        if not path.exists():
            return ToolResult(False, f"delete_file failed: {shown} does not exist")
        if not path.is_file():
            return ToolResult(False, f"delete_file failed: {shown} is not a regular file")
        before = path.read_text(encoding="utf-8", errors="replace")
        return (path, rel, before)

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        _, rel, before = p
        return ToolResult(True, unified_diff(rel, before, ""))

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        p = self._plan(args, ctx)
        if isinstance(p, ToolResult):
            return p
        path, rel, before = p
        ctx.originals.setdefault(rel, before)
        path.unlink()
        return ToolResult(True, f"ok: deleted {args['path']}")


class RunShellTool:
    name = "run_shell"
    description = "Run a shell command with the workspace root as working directory."
    terse_description = "Run a shell command in the workspace."
    args_doc = '{"command": str}'
    parameters: dict = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }
    requires_approval = True
    read_only = False
    MAX_OUTPUT_CHARS = 8000

    def preview(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return ToolResult(True, f"$ {args['command']}")

    def approval_key(self, args: dict[str, Any]) -> str:
        return f"run_shell:{args['command']}"

    def preflight(self, args: dict[str, Any], ctx: ToolContext) -> None:
        tokens = shlex.split(args["command"])
        for tok in tokens[1:]:
            candidates = [tok]
            if "=" in tok:
                candidates.append(tok.rsplit("=", 1)[1])
            for cand in candidates:
                if cand.startswith(("/", "~")) or ".." in Path(cand).parts:
                    ctx.workspace.resolve(cand)

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        timeout = ctx.shell_timeout_s
        mode = approval_mode_of(ctx.approval)
        gate = ctx.gate
        env = gate.shell_env(mode) if gate is not None else None
        if env is None:
            env = {k: v for k, v in os.environ.items() if k not in ctx.hidden_env}
        argv = gate.sandbox_argv(args["command"], mode) if gate is not None else None
        if argv is not None:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=ctx.workspace.root,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                args["command"],
                cwd=ctx.workspace.root,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(False, f"timeout after {timeout}s")
        text = out.decode("utf-8", errors="replace")[-self.MAX_OUTPUT_CHARS :]
        rc = proc.returncode
        return ToolResult(rc == 0, f"exit_code={rc}\n{text}")


def default_tools() -> list[Any]:
    return [
        ListFilesTool(),
        ReadFileTool(),
        SearchTool(),
        EditFileTool(),
        WriteFileTool(),
        DeleteFileTool(),
        RunShellTool(),
        TodoWriteTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitLogTool(),
        GitAddTool(),
        GitCommitTool(),
        GitBranchTool(),
        WebFetchTool(),
    ]
