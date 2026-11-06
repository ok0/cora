from __future__ import annotations

import ast
import re
from pathlib import Path

from cora.core import checks, policy, shellguard, toolchains
from cora.core.shellguard import INTERPRETERS
from cora.core.toolchains import TOOLCHAINS

FIXED_NAMES = frozenset(
    {
        "python", "pypy", "py", "node", "nodejs", "deno", "bun", "ruby", "perl", "php",
        "lua", "luajit", "rscript", "osascript", "pwsh", "powershell", "awk", "gawk",
        "mawk", "nawk", "sed", "sh", "bash", "zsh", "dash", "ksh", "mksh", "fish", "csh",
        "tcsh", "ash", "busybox", "uv", "pip", "pytest", "ruff", "mypy", "unittest",
        "doctest", "compileall", "npm", "npx", "yarn", "pnpm", "cargo", "rustc", "go",
        "java", "javac", "javascript", "typescript", "tsc", "tclsh", "venv",
    }
)

ALLOWLIST: dict[tuple[str, str, str], str] = {
    ("policy.py", "sandbox_argv", "/bin/sh"): (
        "system shell sandbox-exec uses to run the confined command; "
        "infrastructure, not per-interpreter rule data; changing it changes behaviour"
    ),
    ("checks.py", "is_python_workspace", "is_python_workspace"): (
        "public core function name used by agent self-test gating since M18; "
        "renaming changes the API"
    ),
    ("checks.py", "is_python_workspace", "python"): (
        "TOOLCHAINS row key whose file markers decide self-test eligibility; "
        "a data lookup, not a per-toolchain branch"
    ),
}

FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
WORD = re.compile(r"[a-z0-9]+")
SOURCES = {
    "shellguard.py": Path(shellguard.__file__),
    "policy.py": Path(policy.__file__),
    "checks.py": Path(checks.__file__),
    "toolchains.py": Path(toolchains.__file__),
}
PLANTED = '''DATA = {"node": 1}
def f(name):
    """python in a docstring"""
    # bash in a comment
    return name == "node"
def g(x):
    return PY_RE.fullmatch(x)
def h(x):
    return x
def k(x):
    return x == "rust"
'''


def table_names() -> set[str]:
    out: set[str] = set()
    for spec in INTERPRETERS.values():
        out |= spec.names | spec.allowed_modules | spec.redispatch_modules | spec.runner_programs
        if spec.name_pattern is not None:
            out |= set(re.findall(r"[a-z]+", re.sub(r"\\.", "", spec.name_pattern.pattern)))
    return {name.lower() for name in out}


def toolchain_names() -> set[str]:
    out = {tid.lower() for tid in TOOLCHAINS}
    for tc in TOOLCHAINS.values():
        for pattern in (*tc.commands, *tc.file_runs, tc.check_command):
            out.add(pattern.split()[0].lower())
    return out


def forbidden() -> set[str]:
    return table_names() | FIXED_NAMES | toolchain_names()


def _own_items(fn: ast.FunctionDef | ast.AsyncFunctionDef):
    body = list(fn.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    stack: list[ast.AST] = body + list(ast.iter_child_nodes(fn.args))
    while stack:
        node = stack.pop()
        if isinstance(node, FUNC):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield "str", node.value
        elif isinstance(node, ast.Name):
            yield "name", node.id
        elif isinstance(node, ast.Attribute):
            yield "attr", node.attr
        elif isinstance(node, ast.arg):
            yield "arg", node.arg
        elif isinstance(node, ast.keyword) and node.arg is not None:
            yield "kwarg", node.arg
        stack.extend(ast.iter_child_nodes(node))


def _collect(source: str, filename: str) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for fn in (node for node in ast.walk(ast.parse(source)) if isinstance(node, FUNC)):
        out.append((filename, fn.name, "def", fn.name))
        for kind, text in _own_items(fn):
            out.append((filename, fn.name, kind, text))
    return out


def _is_hit(item: tuple[str, str, str, str], names: set[str]) -> bool:
    return bool(set(WORD.findall(item[3].lower())) & names)


def scan(source: str, filename: str, names: set[str]) -> list[tuple[str, str, str, str]]:
    return [
        item
        for item in _collect(source, filename)
        if _is_hit(item, names) and (item[0], item[1], item[3]) not in ALLOWLIST
    ]


def test_control_flow_names_no_interpreter():
    hits: list[tuple[str, str, str, str]] = []
    for filename, path in SOURCES.items():
        hits += scan(path.read_text(encoding="utf-8"), filename, forbidden())
    assert not hits, "interpreter names in control flow:\n" + "\n".join(
        f"{f}:{fn} {kind} {text!r}" for f, fn, kind, text in hits
    )


def test_allowlist_entries_used_and_justified():
    names = forbidden()
    unfiltered = {
        (f, fn, text)
        for filename, path in SOURCES.items()
        for f, fn, _kind, text in _collect(path.read_text(encoding="utf-8"), filename)
        if _is_hit((f, fn, _kind, text), names)
    }
    for key, reason in ALLOWLIST.items():
        assert key in unfiltered, f"allowlist entry unused: {key}"
        assert len(reason) >= 20, f"allowlist reason too short: {key}"


def test_scanner_flags_planted_name():
    found = {(fn, kind, text) for _, fn, kind, text in scan(PLANTED, "planted.py", forbidden())}
    assert found == {("f", "str", "node"), ("g", "name", "PY_RE"), ("k", "str", "rust")}


def test_name_list_derived_from_table():
    derived = {"python", "bash", "sed", "deno", "node", "gawk", "uv", "pytest", "rscript"}
    assert derived <= forbidden()
    assert "gawk" in table_names()
    assert "luajit" in table_names()
    assert {"rust", "make", "python3", "npm", "cargo"} <= toolchain_names()
