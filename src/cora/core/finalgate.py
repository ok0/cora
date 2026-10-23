from __future__ import annotations

import ast
import os
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cora.core.checks import SELFTEST_DIR
from cora.core.policy import WRITE_TOOLS

READ_ONLY_COMMANDS = frozenset(
    {
        "ls",
        "cat",
        "head",
        "tail",
        "grep",
        "rg",
        "find",
        "pwd",
        "echo",
        "wc",
        "tree",
        "which",
        "stat",
        "file",
        "du",
        "df",
        "env",
        "printenv",
        "git",
        "diff",
        "sort",
        "uniq",
        "less",
        "more",
    }
)
SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"})
MAX_FILES = 200
MAX_LINES = 20

VERIFY_FEEDBACK = (
    "Not accepted yet: you edited files, but no check or run command has succeeded "
    "(exit code 0) since your last edit. Run the tests or execute the program with run_shell "
    "to verify the change, fix any failure, then give your Final Answer again."
)
SYNTAX_FEEDBACK = (
    "Not accepted yet: files you edited have syntax errors:\n{lines}\n"
    "Fix them, then give your Final Answer again."
)
SYNTAX_EDIT_NOTE = "Syntax check: {lines}"
EDGE_CASE_FEEDBACK = (
    "Not accepted yet: before finishing, exercise your code on edge inputs - empty input, "
    "input that is only punctuation or whitespace, and boundary values (zero, a single item, "
    "the smallest and largest allowed values, unknown or invalid options or commands). "
    "Run them with run_shell, fix any failure, then give your Final Answer again."
)
STUB_FEEDBACK = (
    "Not accepted yet: these definitions are stubs or were removed by your edits:\n{lines}\n"
    "Implement or restore them, verify, then give your Final Answer again."
)
SEED_SHOW_LINES = 60
OVERWRITE_FEEDBACK = (
    "Not written: {path} existed before this run, contains non-stub code ({lines} lines) "
    "and you have not read it in this run. Its current content:\n{content}\n"
    "If it is a test or specification file, keep it and change the other files until it "
    "passes. If you really mean to replace it, send the same write_file call again."
)


def is_check_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    while tokens and "=" in tokens[0] and tokens[0].split("=", 1)[0].isidentifier():
        tokens = tokens[1:]
    if not tokens:
        return False
    return os.path.basename(tokens[0]) not in READ_ONLY_COMMANDS


@dataclass
class EditTracker:
    edited: list[str] = field(default_factory=list)
    unchecked: bool = False
    pending: list[str] = field(default_factory=list)

    def note(self, name: str, args: Any, ok: bool) -> None:
        if not ok or not isinstance(args, dict):
            return
        if name in WRITE_TOOLS:
            path = args.get("path")
            if isinstance(path, str) and path:
                if path not in self.edited:
                    self.edited.append(path)
                self.pending.append(path)
                self.unchecked = True
        elif name == "run_shell":
            command = args.get("command")
            if isinstance(command, str) and is_check_command(command):
                self.unchecked = False

    def drain(self) -> list[str]:
        out = self.pending
        self.pending = []
        return out


def _resolve(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else root / rel


def syntax_errors(root: Path, paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        p = _resolve(root, rel)
        if not p.is_file():
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        try:
            ast.parse(src, filename=rel)
        except SyntaxError as e:
            out.append(f"{rel}:{e.lineno}: {e.msg}")
        except ValueError:
            continue
    return list(dict.fromkeys(out))


def source_files(root: Path) -> list[str]:
    out: list[str] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") or part in SKIP_DIRS for part in parts):
            continue
        if rel.as_posix().startswith(SELFTEST_DIR + "/"):
            continue
        if any(part in ("tests", "test") for part in parts):
            continue
        name = parts[-1]
        if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
            continue
        out.append(rel.as_posix())
        if len(out) >= MAX_FILES:
            break
    return out


def top_level_defs(path: Path) -> dict[str, int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, SyntaxError):
        return {}
    out: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node.lineno
    return out


def defs_snapshot(root: Path) -> dict[str, dict[str, int]]:
    return {rel: top_level_defs(root / rel) for rel in source_files(root)}


def _decorator_name(d: ast.expr) -> str:
    target = d.func if isinstance(d, ast.Call) else d
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        name = _decorator_name(d)
        if name.endswith("abstractmethod") or name.endswith("overload"):
            return False
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return True
    if len(body) != 1:
        return False
    s = body[0]
    if isinstance(s, ast.Pass):
        return True
    if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
        return True
    if isinstance(s, ast.Raise):
        exc = s.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True
    return False


def _base_name(b: ast.expr) -> str:
    if isinstance(b, ast.Attribute):
        return b.attr
    if isinstance(b, ast.Name):
        return b.id
    return ""


def _collect_stubs(node: ast.AST, rel: str, in_protocol: bool, out: list[str]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not in_protocol and _is_stub(child):
                out.append(f"{rel}:{child.lineno}: {child.name} is a stub")
            _collect_stubs(child, rel, in_protocol, out)
        elif isinstance(child, ast.ClassDef):
            is_proto = in_protocol or any(_base_name(b) == "Protocol" for b in child.bases)
            _collect_stubs(child, rel, is_proto, out)
        else:
            _collect_stubs(child, rel, in_protocol, out)


def _norm(root: Path, p: str) -> str | None:
    try:
        return _resolve(root, p).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def stub_findings(
    root: Path, baseline: dict[str, dict[str, int]], edited: Iterable[str]
) -> list[str]:
    out: list[str] = []
    for rel in source_files(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, SyntaxError):
            continue
        _collect_stubs(tree, rel, False, out)
    edited_set = {n for n in (_norm(root, p) for p in edited) if n is not None}
    for rel, base_defs in baseline.items():
        if _norm(root, rel) not in edited_set:
            continue
        path_now = root / rel
        if not path_now.exists():
            out.append(f"{rel}: file existed before your edits and is now missing")
            continue
        now = top_level_defs(path_now)
        for name, line in base_defs.items():
            if name not in now:
                out.append(f"{rel}:{line}: {name} was defined before your edits and is now missing")
    return list(dict.fromkeys(out))


def format_lines(items: list[str]) -> str:
    body = "\n".join(items[:MAX_LINES])
    if len(items) > MAX_LINES:
        body += f"\n... and {len(items) - MAX_LINES} more"
    return body


def protected_seed_files(root: Path) -> set[str]:
    candidates: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") or part in SKIP_DIRS for part in parts):
            continue
        if rel.as_posix().startswith(SELFTEST_DIR + "/"):
            continue
        candidates.append(p)
        if len(candidates) >= MAX_FILES:
            break
    out: set[str] = set()
    for p in candidates:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError, SyntaxError):
            continue
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_stub(node)
            for node in ast.walk(tree)
        ):
            out.add(p.relative_to(root).as_posix())
    return out


@dataclass
class OverwriteGuard:
    root: Path
    protected: set[str]
    seen: set[str] = field(default_factory=set)
    fired: bool = False

    @classmethod
    def snapshot(cls, root: Path) -> OverwriteGuard:
        return cls(root, protected_seed_files(root))

    def note(self, name: str, args: Any, ok: bool) -> None:
        if not ok or not isinstance(args, dict):
            return
        path = args.get("path")
        if not isinstance(path, str):
            return
        if name == "read_file" or name in WRITE_TOOLS:
            rel = _norm(self.root, path)
            if rel is not None:
                self.seen.add(rel)

    def check(self, name: str, args: Any) -> tuple[str, str] | None:
        if self.fired or name != "write_file" or not isinstance(args, dict):
            return None
        if args.get("append") is True:
            return None
        path = args.get("path")
        if not isinstance(path, str):
            return None
        rel = _norm(self.root, path)
        if rel is None or rel not in self.protected or rel in self.seen:
            return None
        if not (self.root / rel).is_file():
            return None
        text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        self.fired = True
        self.seen.add(rel)
        content = "\n".join(f"{i:>5}| {ln}" for i, ln in enumerate(lines[:SEED_SHOW_LINES], 1))
        if len(lines) > SEED_SHOW_LINES:
            content += "\n...[truncated]"
        return rel, OVERWRITE_FEEDBACK.format(path=rel, lines=len(lines), content=content)
