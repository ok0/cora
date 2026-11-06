"""M22b baseline: classification of today's run_shell allow list and decision snapshots.

Usage (from the project root):
    uv run python tests/m22b_baseline.py allow [--write] [--workspace DIR]
    uv run python tests/m22b_baseline.py decisions --out PATH
    uv run python tests/m22b_baseline.py diff
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

import m22_golden
from cora.core import policy, shellguard

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/m22b"
TODAY = FIX / "allow_today.json"
BASELINE = FIX / "baseline.jsonl"
GOLDEN = FIX / "allow_golden.jsonl"
TEMPLATES = ROOT / "src/cora/bench/e2e_tasks"
MODES = ("default", "strict", "confine")

NEUTRAL_GIT = "git is version control, not a language toolchain"
NEUTRAL_POSIX = "POSIX file/text utility, not a language toolchain"
PY_TEST_RUNNER = "names pytest, the Python test runner"
PY_INTERPRETER = "names the Python interpreter"
PY_UV = "names uv, a Python package runner, with a Python tool"
PY_RUFF = "names ruff, a Python linter"
PY_FILE_RUN = "runs a .py file with the Python interpreter"

CLASSIFICATION: dict[str, tuple[str, str]] = {
    "pytest": ("toolchain:python", PY_TEST_RUNNER),
    "pytest *": ("toolchain:python", PY_TEST_RUNNER),
    "python -m pytest": ("toolchain:python", PY_INTERPRETER),
    "python -m pytest *": ("toolchain:python", PY_INTERPRETER),
    "python3 -m pytest": ("toolchain:python", PY_INTERPRETER),
    "python3 -m pytest *": ("toolchain:python", PY_INTERPRETER),
    "python -m unittest": ("toolchain:python", PY_INTERPRETER),
    "python -m unittest *": ("toolchain:python", PY_INTERPRETER),
    "python3 -m unittest": ("toolchain:python", PY_INTERPRETER),
    "python3 -m unittest *": ("toolchain:python", PY_INTERPRETER),
    "uv run pytest": ("toolchain:python", PY_UV),
    "uv run pytest *": ("toolchain:python", PY_UV),
    "uv run ruff *": ("toolchain:python", PY_UV),
    "ruff": ("toolchain:python", PY_RUFF),
    "ruff *": ("toolchain:python", PY_RUFF),
    "python -m ruff *": ("toolchain:python", PY_INTERPRETER),
    "python3 -m ruff *": ("toolchain:python", PY_INTERPRETER),
    "git status": ("neutral", NEUTRAL_GIT),
    "git status *": ("neutral", NEUTRAL_GIT),
    "git diff": ("neutral", NEUTRAL_GIT),
    "git diff *": ("neutral", NEUTRAL_GIT),
    "git log": ("neutral", NEUTRAL_GIT),
    "git log *": ("neutral", NEUTRAL_GIT),
    "git show": ("neutral", NEUTRAL_GIT),
    "git show *": ("neutral", NEUTRAL_GIT),
    "git branch": ("neutral", NEUTRAL_GIT),
    "git branch -a": ("neutral", NEUTRAL_GIT),
    "git branch -v": ("neutral", NEUTRAL_GIT),
    "git branch -vv": ("neutral", NEUTRAL_GIT),
    "git branch --list": ("neutral", NEUTRAL_GIT),
    "git branch --list *": ("neutral", NEUTRAL_GIT),
    "git branch --show-current": ("neutral", NEUTRAL_GIT),
    "ls": ("neutral", NEUTRAL_POSIX),
    "ls *": ("neutral", NEUTRAL_POSIX),
    "cat *": ("neutral", NEUTRAL_POSIX),
    "grep *": ("neutral", NEUTRAL_POSIX),
    "head *": ("neutral", NEUTRAL_POSIX),
    "tail *": ("neutral", NEUTRAL_POSIX),
    "wc *": ("neutral", NEUTRAL_POSIX),
    "pwd": ("neutral", NEUTRAL_POSIX),
    "echo": ("neutral", NEUTRAL_POSIX),
    "echo *": ("neutral", NEUTRAL_POSIX),
    "python *.py": ("toolchain:python", PY_FILE_RUN),
    "python *.py *": ("toolchain:python", PY_FILE_RUN),
    "python3 *.py": ("toolchain:python", PY_FILE_RUN),
    "python3 *.py *": ("toolchain:python", PY_FILE_RUN),
}

R2_ROWS: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    (
        "m20d-deepseek-v2/e2e_n08-r0",
        "208_n08_contact_dedupe",
        "rm edge_checks.py",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r0",
        "208_n08_contact_dedupe",
        "bash test_cli.sh",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r0",
        "208_n08_contact_dedupe",
        "bash test_cli.sh 2>&1",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "rm -rf contacts/__pycache__ tests/__pycache__ __pycache__",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "python3 -m compileall -f contacts",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "rm debug_norm.py",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "find . -maxdepth 1 -type f -name '*.csv' -o -name 'OUT' -o -name 'OUT.csv'",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "ls -la *.csv 2>/dev/null || true",
        ("deny", "default"),
    ),
    (
        "m20d-deepseek-v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "find . -name '*.csv' -type f",
        ("deny", "default"),
    ),
    ("m20d-deepseek-v2/e2e_h03-r1", "103_h03_escapes", "rm check.py", ("deny", "default")),
    (
        "m20/p2/e2e_h01-r0",
        "101_h01_csv_report",
        "find . -type f -name '*.py' | sort",
        ("deny", "default"),
    ),
    (
        "m20/p2/e2e_h01-r0",
        "101_h01_csv_report",
        "All required files exist with correct module layout",
        ("deny", "default"),
    ),
    (
        "m20/rr/e2e_h01-r2",
        "101_h01_csv_report",
        "The csvreport directory exists and contains parser.py, stats.py, cli.py, "
        "__init__.py, and __main__.py.",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_n08-r1",
        "208_n08_contact_dedupe",
        "test -f contacts/__init__.py && test -f contacts/normalize.py "
        "&& test -f contacts/merge.py && test -f contacts/cli.py",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_n08-r0",
        "208_n08_contact_dedupe",
        "test -f contacts/__init__.py && test -f contacts/normalize.py "
        "&& test -f contacts/merge.py && test -f contacts/cli.py",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_h01-r2",
        "101_h01_csv_report",
        "mkdir -p testdir && python test_cli.py testdir col",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_h01-r0",
        "101_h01_csv_report",
        r"find . -name '*.py' -type f | grep -E 'test.*\.py$'",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_h01-r0",
        "101_h01_csv_report",
        "mv edge_test.py edge_check.py",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_h01-r0",
        "101_h01_csv_report",
        "mkdir -p tmp && mv edge_test.py tmp/",
        ("deny", "default"),
    ),
    (
        "m20/v2/e2e_h01-r0",
        "101_h01_csv_report",
        "mv test_main.py test_main_old.py",
        ("deny", "default"),
    ),
)

_README = "hello\nend\n"
_PY_FILES = {"tests/test_a.py": "def test_a():\n    pass\n", "app.py": "print(1)\n"}
_NODE_FILES = {
    "package.json": '{"name": "w", "scripts": {"test": "node test.js"}}\n',
    "test.js": "console.log(1)\n",
}
_RUST_FILES = {"Cargo.toml": '[package]\nname = "w"\nversion = "0.1.0"\n'}

WS_FILES: dict[str, dict[str, str]] = {
    "none": {"README.md": _README},
    "python": {"README.md": _README, **_PY_FILES},
    "python-wide": {"README.md": _README, "app.py": "print(1)\n"},
    "node": {"README.md": _README, **_NODE_FILES},
    "rust": {"README.md": _README, **_RUST_FILES},
    "go": {"README.md": _README, "go.mod": "module w\n"},
    "make": {"README.md": _README, "Makefile": "test:\n\techo ok\n"},
    "python-node": {"README.md": _README, **_PY_FILES, **_NODE_FILES},
    "node-rust": {"README.md": _README, **_NODE_FILES, **_RUST_FILES},
}

WS_TOOLCHAINS: dict[str, tuple[str, ...]] = {
    "none": (),
    "python": ("python",),
    "python-wide": ("python",),
    "node": ("node",),
    "rust": ("rust",),
    "go": ("go",),
    "make": ("make",),
    "python-node": ("python", "node"),
    "node-rust": ("node", "rust"),
}

PY = (
    "pytest",
    "pytest -q",
    "python -m pytest",
    "python -m pytest -q",
    "python3 -m pytest",
    "python3 -m pytest -q",
    "python -m unittest",
    "python -m unittest -v",
    "python3 -m unittest",
    "python3 -m unittest -v",
    "uv run pytest",
    "uv run pytest -q",
    "uv run ruff check .",
    "ruff",
    "ruff check .",
    "python -m ruff check .",
    "python3 -m ruff check .",
    "python app.py",
    "python app.py x",
    "python3 app.py",
    "python3 app.py x",
)
NEUTRAL = (
    "git status",
    "git status --short",
    "git diff",
    "git diff --stat",
    "git log",
    "git log --oneline",
    "git show",
    "git show HEAD",
    "git branch",
    "git branch -a",
    "git branch -v",
    "git branch -vv",
    "git branch --list",
    "git branch --list x",
    "git branch --show-current",
    "ls",
    "ls -la",
    "cat README.md",
    "grep hello README.md",
    "head -n 1 README.md",
    "tail -n 1 README.md",
    "wc -l README.md",
    "pwd",
    "echo",
    "echo hi",
    "cat README.md | head",
    "cat README.md | wc -l",
)
TOOLCHAIN = ("npm test", "cargo test", "go test ./...", "make test")
NEAR_MISS = (
    "npm test -- --watch",
    "npm run test",
    "npm install",
    "npx jest",
    "cargo test --release",
    "cargo run",
    "go test ./pkg",
    "go run main.go",
    "make",
    "make test V=1",
    "make build",
)
INLINE = (
    "python -c 1",
    "python3 -c 1",
    "node -e 1",
    "node -p 1",
    "perl -e 1",
    "deno eval 1",
    "python -m http.server",
    "bash test.sh",
    "sh -c ls",
)
R3 = (
    "rm app.py",
    "find . -name '*.py'",
    "mkdir out",
    "python3 -m compileall -f .",
    "true",
    "test -f README.md",
)
CORPUS: tuple[str, ...] = PY + NEUTRAL + TOOLCHAIN + NEAR_MISS + INLINE + R3

INLINE_RULES = frozenset(
    {
        "confine:one-liner",
        "confine:interpreter-stdin",
        "confine:shell-c",
        "confine:eval",
        "confine:python-module",
        "confine:indirect",
        "confine:wrapper",
        "confine:xargs",
        "confine:source",
        "confine:uv-run",
        "confine:python-option",
    }
)
GAP_COMMANDS = (
    "busybox sh -c ls",
    "deno -A eval x",
    "pwsh -Comm x",
    "pwsh -ec x",
    "node -pe x",
    "perl -pe x README.md",
    "ruby -ne x",
)


def build_workspaces(base: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for name, files in WS_FILES.items():
        root = base / name
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        out[name] = Path(os.path.realpath(root))
    return out


def effective(profile: str, workspace: Path) -> tuple[str, ...]:
    if hasattr(policy, "builtin_shell_allow"):
        return tuple(policy.builtin_shell_allow(workspace))
    rules = policy.STRICT_RULES if profile == "strict" else policy.DEFAULT_RULES
    rule_id = f"{profile}:shell"
    for rule in rules:
        if rule.id == rule_id:
            return tuple(rule.commands)
    raise KeyError(rule_id)


def inline_corpus() -> tuple[str, ...]:
    _, records = m22_golden.load_golden()
    kept: list[str] = []
    for rec in records:
        segments = rec["analyze"]["segments"]
        findings = [f[0] for f in rec["analyze"]["findings"]]
        for seg in segments:
            findings.extend(f[0] for f in seg["findings"])
        hit = any(rule in INLINE_RULES for rule in findings) or any(
            seg["argv"] and shellguard.interpreter_for(Path(seg["argv"][0]).name) is not None
            for seg in segments
        )
        if hit and rec["command"] not in kept:
            kept.append(rec["command"])
    for cmd in GAP_COMMANDS:
        if cmd not in kept:
            kept.append(cmd)
    return tuple(cmd for cmd in kept if cmd not in CORPUS)


def _verdict(v: Any) -> list:
    return [v.decision, v.rule, v.reason, v.hard]


def decisions(base: Path) -> tuple[dict, list[dict]]:
    real = Path(os.path.realpath(base))
    (real / "home").mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("HOME")
    os.environ["HOME"] = str(real / "home")
    try:
        workspaces = build_workspaces(real)
        engines: dict[str, tuple[Any, Any]] = {}
        for name, ws in workspaces.items():
            guard = shellguard.PathGuard(ws, shellguard.default_protected())
            engines[name] = (
                policy.PolicyEngine(policy.PolicySettings(), guard),
                policy.PolicyEngine(policy.PolicySettings(), guard, strict=True),
            )
    finally:
        if previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous
    pkg = os.path.realpath(str(resources.files("cora")))
    pairs = [(str(real), "<BASE>"), (pkg, "<PKG>"), (str(ROOT), "<REPO>")]
    subs = sorted(pairs, key=lambda p: len(p[0]), reverse=True)
    inline = inline_corpus()

    records: list[dict] = []
    for source, commands in (("corpus", CORPUS), ("inline", inline)):
        for command in commands:
            ws_rows: dict[str, dict[str, list]] = {}
            for name, (default_engine, strict_engine) in engines.items():
                ws_rows[name] = {
                    "default": _verdict(default_engine.evaluate("run_shell", {"command": command})),
                    "strict": _verdict(strict_engine.evaluate("run_shell", {"command": command})),
                    "confine": _verdict(default_engine.confine(command)),
                }
            rec = {"command": command, "source": source, "ws": ws_rows}
            records.append(m22_golden.sanitize(rec, subs))

    header = {
        "kind": "header",
        "generated_from": m22_golden._git_head(),
        "platform": sys.platform,
        "workspaces": list(WS_FILES),
        "modes": list(MODES),
        "sources": {"corpus": len(CORPUS), "inline": len(inline)},
        "total": len(CORPUS) + len(inline),
    }
    return header, records


def write_jsonl(path: Path, header: dict, records: list[dict]) -> None:
    lines = [json.dumps(header, sort_keys=True, ensure_ascii=False)]
    lines.extend(json.dumps(rec, sort_keys=True, ensure_ascii=False) for rec in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> tuple[dict, list[dict]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def diff_rows(old: list[dict], new: list[dict]) -> list[tuple[str, str, str, list, list]]:
    old_by_cmd = {rec["command"]: rec for rec in old}
    rows: list[tuple[str, str, str, list, list]] = []
    for rec in new:
        prev = old_by_cmd.get(rec["command"])
        if prev is None:
            continue
        for ws, modes in rec["ws"].items():
            for mode, verdict in modes.items():
                before = prev["ws"][ws][mode]
                if before != verdict:
                    rows.append((rec["command"], ws, mode, before, verdict))
    return rows


def _fmt(verdict: list) -> str:
    return f"{verdict[0]} {verdict[1]}".replace("|", "\\|")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M22b shell allow baseline tool")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_allow = sub.add_parser("allow")
    p_allow.add_argument("--write", action="store_true")
    p_allow.add_argument("--workspace", type=Path)
    p_dec = sub.add_parser("decisions")
    p_dec.add_argument("--out", type=Path, required=True)
    sub.add_parser("diff")
    args = parser.parse_args(argv)

    if args.cmd == "allow":
        with tempfile.TemporaryDirectory() as td:
            ws = args.workspace or build_workspaces(Path(td) / "syn")["python"]
            payload = {profile: list(effective(profile, ws)) for profile in ("default", "strict")}
        text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
        if args.write:
            TODAY.parent.mkdir(parents=True, exist_ok=True)
            TODAY.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0

    if args.cmd == "decisions":
        with tempfile.TemporaryDirectory() as td:
            header, records = decisions(Path(td))
        write_jsonl(args.out, header, records)
        print(f"wrote {len(records)} records to {args.out}")
        return 0

    old_header, old = load_jsonl(BASELINE)
    _, new = load_jsonl(GOLDEN)
    order = {name: i for i, name in enumerate(old_header["workspaces"])}
    rows = sorted(diff_rows(old, new), key=lambda r: order.get(r[1], len(order)))
    print("| workspace | profile | command | before | after |")
    print("|---|---|---|---|---|")
    for command, ws, mode, before, after in rows:
        cmd = command.replace("|", "\\|")
        print(f"| {ws} | {mode} | `{cmd}` | {_fmt(before)} | {_fmt(after)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
