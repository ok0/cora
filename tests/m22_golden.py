from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

import m22c_cases
from cora.core import policy, shellguard

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/fixtures/m22/shell_golden.jsonl"
MODES = ("default", "strict", "confine", "unlock")
UNLOCK_RULES = [
    {"decision": "allow", "command": c}
    for c in (
        "curl https://example.com/*",
        "python -c *",
        "python3 -m *",
        "node -e *",
        "bash -c *",
        "perl -e *",
        "sed *",
        "awk *",
        "deno eval *",
        "uv run *",
    )
]
OPERATOR_CHARS = set("();<>|&")


def build_box(base: Path) -> Path:
    outside = base / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    ws = base / "ws"
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / ".git").mkdir(parents=True, exist_ok=True)
    (ws / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (ws / "README.md").write_text("hello\nend\n", encoding="utf-8")
    (ws / "script.py").write_text("print(1)\n", encoding="utf-8")
    (ws / "env.sh").write_text("export A=1\n", encoding="utf-8")
    (ws / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (ws / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    (base / "home").mkdir(parents=True, exist_ok=True)
    for name, target in (("link", outside / "secret.txt"), ("linkdir", outside)):
        link = ws / name
        if not link.is_symlink():
            link.symlink_to(target)
    return ws


def sanitize(obj: Any, subs: list[tuple[str, str]]) -> Any:
    if isinstance(obj, dict):
        return {k: sanitize(v, subs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, subs) for v in obj]
    if isinstance(obj, str):
        for old, new in subs:
            obj = obj.replace(old, new)
        return obj
    return obj


class Evaluator:
    def __init__(self, base: Path) -> None:
        self.base = Path(os.path.realpath(base))
        ws = build_box(self.base)
        previous = os.environ.get("HOME")
        os.environ["HOME"] = str(self.base / "home")
        try:
            guard = shellguard.PathGuard(ws, shellguard.default_protected())
        finally:
            if previous is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous
        self.guard = guard
        self.default = policy.PolicyEngine(policy.PolicySettings(), guard)
        self.strict = policy.PolicyEngine(policy.PolicySettings(), guard, strict=True)
        self.unlock = policy.PolicyEngine(
            policy.parse_policy({"rules": UNLOCK_RULES}, "m22-golden"), guard
        )
        pkg = os.path.realpath(str(resources.files("cora")))
        pairs = [(str(self.base), "<BASE>"), (pkg, "<PKG>"), (str(ROOT), "<REPO>")]
        self.subs = sorted(pairs, key=lambda p: len(p[0]), reverse=True)

    def record(self, command: str) -> dict:
        analysis = shellguard.analyze(command, self.guard)

        def verdict(v: Any) -> list:
            return [v.decision, v.rule, v.reason, v.hard]

        def decide(engine: Any) -> list:
            return verdict(engine.evaluate("run_shell", {"command": command}))

        rec = {
            "analyze": {
                "findings": [[f.rule, f.severity, f.reason] for f in analysis.findings],
                "segments": [
                    {
                        "argv": seg.argv,
                        "piped": seg.piped,
                        "findings": [[f.rule, f.severity, f.reason] for f in seg.findings],
                        "table_key": shellguard.table_key(seg.argv),
                    }
                    for seg in analysis.segments
                ],
            },
            "default": decide(self.default),
            "strict": decide(self.strict),
            "confine": verdict(self.default.confine(command)),
            "unlock": decide(self.unlock),
        }
        return sanitize(rec, self.subs)


def tokens(command: str) -> list[str] | None:
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        return None


def segments(command: str) -> list[list[str]]:
    toks = tokens(command)
    if toks is None:
        return []
    out: list[list[str]] = [[]]
    for tok in toks:
        if tok and all(ch in OPERATOR_CHARS for ch in tok):
            out.append([])
        else:
            out[-1].append(tok)
    return [seg for seg in out if seg]


def _test_literals() -> tuple[dict[str, list[str]], int]:
    keywords = ("shellguard", "PolicyEngine", "PolicyGate", "run_shell")
    found: dict[str, list[str]] = {}
    skipped_dynamic = 0
    # Golden predates M22 tests; M22, M22b and M22c test files are not corpus sources.
    for path in sorted(
        p for p in (ROOT / "tests").glob("test_*.py") if not p.name.startswith("test_m22")
    ):
        text = path.read_text(encoding="utf-8")
        if not any(k in text for k in keywords):
            continue
        tree = ast.parse(text, filename=str(path))
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstrings.add(id(body[0].value))
        tag = f"tests:{path.name}"
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                skipped_dynamic += 1
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings or node.value.strip() == "":
                    continue
                found.setdefault(tag, []).append(node.value)
    return found, skipped_dynamic


def _adversarial_scan() -> tuple[list[tuple[str, str]], list[dict]]:
    commands: list[tuple[str, str]] = []
    blocked: list[dict] = []
    for fname in ("test_shell_confinement.py", "test_shell_coverage.py"):
        rel = f"tests/{fname}"
        path = ROOT / rel
        if not path.exists():
            blocked.append({"source": rel, "reason": "missing file"})
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        target = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "ADVERSARIAL_DENY" for t in node.targets
            ):
                target = node
                break
        if target is None:
            blocked.append({"source": rel, "reason": "missing ADVERSARIAL_DENY"})
            continue
        for sub in ast.walk(target.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                commands.append((f"adversarial:{fname}", sub.value))
    return commands, blocked


def _adversarial() -> list[str]:
    return [c for _, c in _adversarial_scan()[0]]


def _fixture_scan() -> tuple[list[tuple[str, str]], int, list[dict]]:
    pairs: list[tuple[str, str]] = []
    unparsed = 0
    blocked: list[dict] = []

    def parse_command(args: Any) -> str | None:
        try:
            value = json.loads(args)["command"]
        except (ValueError, KeyError, TypeError):
            return None
        return value if isinstance(value, str) else None

    m20_dir = ROOT / "tests/fixtures/m20/artifacts"
    if not m20_dir.is_dir():
        blocked.append({"source": "tests/fixtures/m20/artifacts", "reason": "missing directory"})
    else:
        for path in sorted(m20_dir.rglob("events.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("type") == "policy_decision" and ev.get("tool") == "run_shell":
                    pairs.append(("m20:policy_decision", ev["args"]))
                elif ev.get("type") == "tool_call" and ev.get("tool") == "run_shell":
                    cmd = parse_command(ev.get("args"))
                    if cmd is None:
                        unparsed += 1
                    else:
                        pairs.append(("m20:tool_call", cmd))

    m20d_dir = ROOT / "tests/fixtures/m20d/artifacts"
    if not m20d_dir.is_dir():
        blocked.append({"source": "tests/fixtures/m20d/artifacts", "reason": "missing directory"})
    else:
        for path in sorted(m20d_dir.rglob("events.jsonl")):
            posix = path.as_posix()
            if "/e2e_n08-" in posix:
                t = "n08"
            elif "/e2e_h03-" in posix:
                t = "h03"
            else:
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("type") == "policy_decision" and ev.get("tool") == "run_shell":
                    if ev.get("decision") == "deny":
                        pairs.append((f"m20d:{t}:deny", ev["args"]))
                elif ev.get("type") == "tool_call" and ev.get("tool") == "run_shell":
                    cmd = parse_command(ev.get("args"))
                    if cmd is None:
                        unparsed += 1
                    else:
                        pairs.append((f"m20d:{t}:tool_call", cmd))
    return pairs, unparsed, blocked


def _fixture_commands() -> tuple[list[tuple[str, str]], int]:
    pairs, unparsed, _ = _fixture_scan()
    return pairs, unparsed


SHELL_NAMES = "sh bash zsh dash ksh mksh fish csh tcsh ash busybox".split()
PY_NAMES = "python python3 python3.12 python2 pypy pypy3 pypy3.10".split()
PY_MODULES = (
    "pytest unittest ruff mypy py_compile compileall doctest http.server pip venv "
    "pytest_cov Pytest ls echo py.test"
).split()
PY_LETTERS = "B E I s S u q O b".split()
AWK_NAMES = "awk gawk mawk nawk".split()
FLAG_TABLE = {
    "node": ["-e", "--eval", "-p", "--print", "-i", "--interactive", "-r", "--require"],
    "nodejs": ["-e", "--eval", "-p", "--print", "-i", "--interactive", "-r", "--require"],
    "bun": ["-e", "--eval", "-p", "--print"],
    "ruby": ["-e"],
    "perl": ["-e", "-E"],
    "php": ["-r", "-a"],
    "lua": ["-e"],
    "luajit": ["-e"],
    "Rscript": ["-e"],
    "osascript": ["-e"],
    "pwsh": ["-c", "-command", "-encodedcommand"],
}


def generated() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def add(family: str, cmds: list[str]) -> None:
        out.extend((f"generated:{family}", c) for c in cmds)

    shell: list[str] = []
    for n in SHELL_NAMES:
        shell += [
            f"{n} -c 'ls'",
            f"{n} script.sh",
            n,
            f"{n} -s",
            f"{n} -",
            f"{n} -x script.sh",
            f"{n} +x script.sh",
        ]
    shell += [
        "bash -lc ls",
        "bash -xc ls",
        "bash +c ls",
        "bash -cx ls",
        "bash --norc script.sh",
        "bash --norc",
        "bash --norc -c ls",
        "bash -i",
        "bash -x",
        "bash -- script.sh",
        "bash -c",
        "sh -e -c ls",
        "echo ls | bash",
        "echo ls | sh -s",
        "cat env.sh | bash -",
        "ls |& bash",
        "/bin/bash -c ls",
        "/bin/sh script.sh",
        "env bash -c ls",
        "busybox sh -c ls",
        "bash '-c' ls",
        "bash5 -c ls",
        "bashful -c ls",
        "Bash -c ls",
        "shx -c ls",
    ]
    add("shell", shell)

    python: list[str] = []
    for n in PY_NAMES:
        python += [f"{n} -c 'print(1)'", f"{n} script.py", f"{n} -m pytest -q", n, f"{n} -"]
    python += [
        "python3.12.1 -c x",
        "ipython -c x",
        "Python3 -c x",
        "python-config --help",
        "pythonw -c x",
        "py -c x",
        "cpython -c x",
        "python3x -c x",
    ]
    for m in PY_MODULES:
        python += [f"python -m {m}", f"python3 -m{m}"]
    for ch in PY_LETTERS:
        python.append(f"python -{ch} script.py")
    python += [
        "python -BE script.py",
        "python -Bc 'x'",
        "python -IBc x",
        "python -cprint(1)",
        "python -Bm pytest",
        "python -mpytest -q",
        "python -B -m pytest",
        "python -X dev script.py",
        "python -W error script.py",
        "python -C x",
        "python -M pytest",
        "python --version",
        "python --help",
        "python -- script.py",
        "python --",
        "python -B",
        "python -m",
        "python -m pytest --pdb",
        "python -m pytest -p no:cacheprovider",
        "python -m pytest -p evil",
        "python -m ruff --config x.toml check .",
        "python -m ruff check .",
        "python -m ruff format",
        "python -m pytest tests/test_a.py::test_a",
        "python -m pytest ../outside",
        "python3 tests/run.py arg",
        "python script.py arg -c x",
        "python -s -c x",
        "python - script.py",
        "echo x | python",
        "echo x | python -",
        "echo x | python script.py",
        "cat script.py | python3 -B",
        "ls | python",
        "python script.py < README.md",
        "/usr/bin/python3 -c x",
        "./python -c x",
        "python src/app.py",
        "python ../outside/x.py",
        "python script.pyc",
        "python -script.py",
    ]
    add("python", python)

    add(
        "uv",
        [
            "uv run pytest -q",
            "uv run pytest --pdb",
            "uv run ruff check .",
            "uv run ruff format --config x",
            "uv run python -m pytest",
            "uv run python -m pytest -q tests",
            "uv run python3 -m ruff check .",
            "uv run python -m mypy src",
            "uv run python -m unittest",
            "uv run python script.py",
            "uv run python3 script.py arg",
            "uv run python -B script.py",
            "uv run python -c 1",
            "uv run python",
            "uv run python -",
            "uv run /usr/bin/python script.py",
            "uv run node script.js",
            "uv run",
            "uv run mypy src",
            "uv run python -script.py",
            "uv run python -mpytest",
            "uv pip install x",
            "uv sync",
            "uv run uv run pytest",
            "uv run bash -c ls",
            "env uv run pytest",
            "uvx pytest",
            "/opt/bin/uv run pytest -q",
            "uv run pypy3 -m pytest",
            "uv run python3.12 script.py",
        ],
    )

    awk: list[str] = []
    for n in AWK_NAMES:
        awk += [f"{n} 'NR==1' README.md", f"{n} -f prog.awk README.md", f"echo a | {n} 'NR==1'"]
    awk += ["awkx 'NR==1' README.md", "Awk x"]
    add("awk", awk)

    add(
        "sed",
        [
            "sed -n '1,5p' README.md",
            "sed -n '$p' README.md",
            "sed '3d' README.md",
            "sed -n '/foo/p' README.md",
            "sed 's/a/b/g' README.md",
            "sed 's|a|b|' README.md",
            "sed -e 's/a/b/' -e '1p' README.md",
            "sed --expression='s/a/b/' README.md",
            "sed --expression 1p README.md",
            "sed -ne 1p README.md",
            "sed -n'1p' README.md",
            "sed '1p;2p' README.md",
            "sed -E 's/a/b/' README.md",
            "sed -f script.sed README.md",
            "sed --file=x README.md",
            "sed --file x README.md",
            "sed -nf x README.md",
            "sed -i 's/a/b/' README.md",
            "sed 'w out.txt' README.md",
            "sed 'e ls' README.md",
            "sed '1p; s/x/y/w out' README.md",
            "sed 'y/abcdefghijklmnopqrstuvwxyzabcdefghijklmnop/"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMNOP/' README.md",
            "sed -n",
            "sed",
            "gsed 's/a/b/' README.md",
        ],
    )

    add(
        "deno",
        [
            "deno eval 'console.log(1)'",
            "deno repl",
            "deno",
            "deno run script.ts",
            "deno test",
            "deno fmt",
            "deno -A eval x",
            "/usr/local/bin/deno eval x",
            "echo x | deno",
            "denox eval x",
        ],
    )

    flags: list[str] = []
    for n, fl in FLAG_TABLE.items():
        for f in fl:
            flags.append(f"{n} {f} 'x'")
        for f in fl:
            if f.startswith("--"):
                flags.append(f"{n} {f}=x")
        flags += [
            n,
            f"{n} -w",
            f"{n} script.x",
            f"{n} --version",
            f"echo x | {n}",
            f"/usr/bin/{n} {fl[0]} x",
            f"{n} {fl[0].upper()} x",
        ]
    flags += [
        "pwsh -Command x",
        "pwsh -EncodedCommand x",
        "pwsh -Comm x",
        "pwsh -ec x",
        "pwsh -File s.ps1",
        "node -pe x",
        "perl -ne 'print' README.md",
        "perl -pe x README.md",
        "ruby -ne x",
        "node --EVAL=x",
        "php script.php",
        "perl -w script.pl",
        "node18 -e x",
        "Node -e x",
        "nodemon -e x",
        "rscript -e x",
    ]
    add("flags", flags)

    add(
        "wrapper",
        [
            "env node -e x",
            "env PYTHONHASHSEED=0 python -c x",
            "PYTHONHASHSEED=0 python -c x",
            "PYTHONHASHSEED=0 python -m pytest -q",
            "time python -c x",
            "time -p python script.py",
            "nice -n 5 perl -e x",
            "nice python -m pytest",
            "timeout 5 bash -c ls",
            "timeout -s KILL 5 python -c x",
            "command python -m pytest",
            "command -p sh -c ls",
            "exec ruby -e x",
            "nohup lua -e x",
            "builtin sh -c x",
            "stdbuf -o0 python -c x",
            "/usr/bin/env python3 -c x",
            "env -i python -c x",
            "sudo python -c x",
            "xargs python -c x",
        ],
    )

    add(
        "separator",
        [
            "ls; python -c x",
            "ls && node -e x",
            "cat README.md | perl -e x",
            "(python -c x)",
            "python -c x > out.txt",
            "python script.py 2>&1",
            "pytest -q || python -m pytest",
            "python -c x; ls",
            "ls | sh",
            "python -m pytest -q && ruff check .",
            "python -c x &",
            "{ python -c x; }",
            "python -c x;",
            "; python -c x",
        ],
    )

    add(
        "quoting",
        [
            "'python' -c x",
            '"node" -e x',
            r"py\thon -c x",
            'python -c"x"',
            "python '-c' x",
            'python -"c" x',
            '""',
            '"   "',
        ],
    )
    add("m22c", list(m22c_cases.ALL))
    return out


def collect() -> tuple[list[dict], dict]:
    found, skipped_dynamic = _test_literals()
    tagged: list[tuple[str, str]] = []
    for tag in sorted(found):
        tagged.extend((tag, c) for c in found[tag])
    adv, adv_blocked = _adversarial_scan()
    tagged.extend(adv)
    fix_pairs, unparsed, fix_blocked = _fixture_scan()
    tagged.extend(fix_pairs)
    tagged.extend(generated())

    merged: dict[str, set[str]] = {}
    for tag, cmd in tagged:
        merged.setdefault(cmd, set()).add(tag)
    items = [{"command": c, "sources": sorted(tags)} for c, tags in merged.items()]

    counts: dict[str, int] = {}
    categories: dict[str, int] = {}
    for item in items:
        for tag in item["sources"]:
            counts[tag] = counts.get(tag, 0) + 1
        prefixes = {tag.split(":", 1)[0] for tag in item["sources"]}
        for prefix in prefixes:
            categories[prefix] = categories.get(prefix, 0) + 1

    meta = {
        "counts": dict(sorted(counts.items())),
        "categories": dict(sorted(categories.items())),
        "total": len(items),
        "blocked": adv_blocked + fix_blocked,
        "skipped_dynamic": skipped_dynamic,
        "unparsed_tool_args": unparsed,
    }
    return items, meta


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(base: Path) -> list[str]:
    items, meta = collect()
    header = {
        "kind": "header",
        "platform": sys.platform,
        "generated_from": _git_head(),
        "shellguard_sha256": _sha256(ROOT / "src/cora/core/shellguard.py"),
        "policy_sha256": _sha256(ROOT / "src/cora/core/policy.py"),
        "modes": list(MODES),
        **meta,
    }
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    evaluator = Evaluator(base)
    for item in items:
        row = {"command": item["command"], "sources": item["sources"]}
        row.update(evaluator.record(item["command"]))
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return lines


def load_golden() -> tuple[dict, list[dict]]:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:] if line.strip()]
    return header, records


def _write() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        lines = build(Path(tmp))
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def _check() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fresh = build(Path(tmp))
    _, old = load_golden()
    new = [json.loads(line) for line in fresh[1:]]
    diffs = [o["command"] for o, n in zip(old, new, strict=False) if o != n]
    if len(old) != len(new):
        print(f"record count differs: golden={len(old)} fresh={len(new)}")
    if diffs or len(old) != len(new):
        for command in diffs[:20]:
            print(command)
        return 1
    print(f"ok: {len(new)} records match")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M22 shellguard golden corpus")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        return _write()
    if args.check:
        return _check()
    _, meta = collect()
    print(
        json.dumps(
            {
                "categories": meta["categories"],
                "counts": meta["counts"],
                "blocked": meta["blocked"],
                "skipped_dynamic": meta["skipped_dynamic"],
                "unparsed_tool_args": meta["unparsed_tool_args"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
