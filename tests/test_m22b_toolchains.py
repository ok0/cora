from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import m22b_baseline as b
from cora.core import checks, policy, toolchains
from cora.core.checks import detect_check_command, present_toolchains
from cora.core.policy import (
    ALLOW_PREFIX,
    SHELL_ALLOW,
    PolicyEngine,
    PolicyGate,
    PolicySettings,
    builtin_shell_allow,
    load_policy,
    planning_policy,
    render_policy_rules,
)
from cora.core.shellguard import PathGuard, default_protected
from cora.core.toolchains import TOOLCHAINS
from test_policy_hints import NEUTRAL_RE

CORE = Path(checks.__file__).resolve().parent
EXCLUDED = {"project.py": "draft_guide CORA.md template, not policy or check detection"}
MARKER_LITERALS = ("Cargo.toml", "go.mod", "package.json", "setup.cfg")
BANNED_TOKENS = frozenset({"-c", "-e", "-p", "-pe", "-ne", "eval", "-"})
PROFILES = ("default", "strict")


def ws(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "ws"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return Path(root.resolve())


def decide(root: Path, cmd: str, strict: bool = False):
    engine = PolicyEngine(PolicySettings(), PathGuard(root, default_protected()), strict=strict)
    return engine.evaluate("run_shell", {"command": cmd})


@pytest.mark.parametrize("name", ["node", "rust", "go", "make"])
def test_toolchain_workspace_allows_check_command(tmp_path: Path, name: str) -> None:
    root = ws(tmp_path, b.WS_FILES[name])
    tc = TOOLCHAINS[name]
    assert detect_check_command(root) == tc.check_command
    for strict in (False, True):
        v = decide(root, tc.check_command, strict=strict)
        assert v.decision == "allow"
        assert v.rule == ("strict:shell" if strict else "default:shell")
        for cmd in ("pytest", "python app.py"):
            v = decide(root, cmd, strict=strict)
            assert (v.decision, v.rule) == ("deny", "default")
    assert builtin_shell_allow(root) == (*tc.commands, *SHELL_ALLOW)


def test_no_marker_neutral_only(tmp_path: Path) -> None:
    root = ws(tmp_path, b.WS_FILES["none"])
    assert builtin_shell_allow(root) == SHELL_ALLOW
    for cmd in ("pytest", "npm test", "cargo test"):
        for strict in (False, True):
            v = decide(root, cmd, strict=strict)
            assert (v.decision, v.rule) == ("deny", "default"), cmd


def test_two_markers_union(tmp_path: Path) -> None:
    node_rust = ws(tmp_path / "nr", b.WS_FILES["node-rust"])
    assert builtin_shell_allow(node_rust) == ("npm test", "cargo test", *SHELL_ALLOW)
    python_node = ws(tmp_path / "pn", b.WS_FILES["python-node"])
    py = TOOLCHAINS["python"]
    assert builtin_shell_allow(python_node) == (
        *py.commands, "npm test", *SHELL_ALLOW, *py.file_runs)


def test_non_markers(tmp_path: Path) -> None:
    scripts = {"name": "w", "scripts": {"test": 'echo "Error: no test specified" && exit 1'}}
    cases = {
        "placeholder-npm": {"package.json": json.dumps(scripts)},
        "make-build": {"Makefile": "build:\n\techo\n"},
        "make-variable": {"Makefile": "test := 1\n"},
    }
    for name, files in cases.items():
        root = ws(tmp_path / name, files)
        assert builtin_shell_allow(root) == SHELL_ALLOW, name


def test_marker_created_mid_run(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    root = Path(empty.resolve())
    gate = PolicyGate(PolicySettings(), root)
    assert gate.verdict("run_shell", {"command": "cargo test"}, "policy").decision == "deny"
    (root / "Cargo.toml").write_text('[package]\nname = "w"\n', encoding="utf-8")
    assert gate.verdict("run_shell", {"command": "cargo test"}, "policy").decision == "allow"
    assert gate.verdict("run_shell", {"command": "pytest -q"}, "policy").decision == "deny"
    (root / "tests").mkdir()
    assert gate.verdict("run_shell", {"command": "pytest -q"}, "policy").decision == "allow"


def test_user_rule_escape_hatch(tmp_path: Path) -> None:
    root = Path((tmp_path / "esc").resolve())
    root.mkdir()
    (root / ".cora").mkdir()
    (root / ".cora" / "policy.toml").write_text(
        '[[rules]]\nid = "user-pytest"\ndecision = "allow"\ncommand = ["pytest *"]\n',
        encoding="utf-8")
    settings = load_policy(PolicySettings(), root)
    engine = PolicyEngine(settings, PathGuard(root, default_protected()))
    v = engine.evaluate("run_shell", {"command": "pytest -q"})
    assert (v.decision, v.rule) == ("allow", "user-pytest")
    strict = PolicyEngine(settings, PathGuard(root, default_protected()), strict=True)
    assert strict.evaluate("run_shell", {"command": "pytest -q"}).decision == "deny"


def test_shared_effective_function(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(policy, "builtin_shell_allow", lambda w: ("only-this *",))
    root = Path(tmp_path.resolve())
    for strict in (False, True):
        assert decide(root, "only-this x", strict=strict).decision == "allow"
    plan = planning_policy(PolicySettings(), root, "policy")
    assert plan is not None
    assert plan.verdict("only-this x").decision == "allow"
    first = render_policy_rules(PolicySettings(), approval_mode="policy", workspace=root)
    assert first.split("\n")[0] == ALLOW_PREFIX + "only-this *"


def test_render_by_workspace(tmp_path: Path) -> None:
    today = json.loads(b.TODAY.read_text(encoding="utf-8"))
    py_root = b.build_workspaces(tmp_path / "syn")["python"]
    node_root = ws(tmp_path / "node", b.WS_FILES["node"])
    none_root = ws(tmp_path / "none", b.WS_FILES["none"])
    expected = {
        py_root: ALLOW_PREFIX + ", ".join(today["default"]),
        node_root: ALLOW_PREFIX + ", ".join(("npm test", *SHELL_ALLOW)),
        none_root: ALLOW_PREFIX + ", ".join(SHELL_ALLOW),
    }
    for root, first in expected.items():
        text = render_policy_rules(PolicySettings(), approval_mode="policy", workspace=root)
        lines = text.split("\n")
        assert lines[0] == first
        assert not any(NEUTRAL_RE.search(line) for line in lines[1:])


def test_table_matches_classification() -> None:
    assert SHELL_ALLOW == tuple(
        k for k, (kind, _) in b.CLASSIFICATION.items() if kind == "neutral")
    py = TOOLCHAINS["python"]
    assert (*py.commands, *py.file_runs) == tuple(
        k for k, (kind, _) in b.CLASSIFICATION.items() if kind == "toolchain:python")
    for tid, tc in TOOLCHAINS.items():
        if tid != "python":
            assert tc.commands == (tc.check_command,), tid
    patterns = [*SHELL_ALLOW]
    for tc in TOOLCHAINS.values():
        patterns.extend((*tc.commands, *tc.file_runs))
    for pattern in patterns:
        assert not (set(pattern.split()) & BANNED_TOKENS), pattern


def test_marker_constant_single() -> None:
    assert not hasattr(checks, "PYTHON_MARKERS")
    assert checks.PYTEST_COMMAND is toolchains.PYTEST_COMMAND
    found: dict[str, set[str]] = {}
    for path in CORE.rglob("*.py"):
        if path.name in EXCLUDED or path.name == "toolchains.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in MARKER_LITERALS:
                found.setdefault(node.value, set()).add(path.name)
    assert not found, found


def test_present_toolchains_of_synthetic_workspaces(tmp_path: Path) -> None:
    built = b.build_workspaces(tmp_path / "syn")
    for name, root in built.items():
        assert present_toolchains(root) == b.WS_TOOLCHAINS[name], name
