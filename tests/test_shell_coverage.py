from __future__ import annotations

import asyncio
import shlex
from importlib import resources

import pytest

from cora.core import shellguard
from cora.core.policy import (
    SHELL_ALLOW,
    PolicyEngine,
    PolicySettings,
    Rule,
)
from cora.core.shellguard import PROGRAM_SPECS, PathGuard, default_protected
from cora.core.toolchains import TOOLCHAINS
from cora.core.tools import ApprovalPolicy, ToolContext
from cora.core.tools.base import Workspace
from cora.core.tools.builtin import SearchTool

PKG_DATA = str(resources.files("cora") / "data")
PKG_E2E = str(resources.files("cora") / "bench" / "e2e_tasks")


@pytest.fixture(scope="module")
def box(tmp_path_factory):
    base = tmp_path_factory.mktemp("coverage")
    (base / "outside").mkdir()
    (base / "outside" / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    ws = base / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "tests").mkdir()
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (ws / ".cora").mkdir()
    (ws / "README.md").write_text("hello\nend\n", encoding="utf-8")
    (ws / "script.py").write_text("print(1)\n", encoding="utf-8")
    (ws / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (ws / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    (ws / "link").symlink_to(base / "outside" / "secret.txt")
    (ws / "linkdir").symlink_to(base / "outside")
    return PolicyEngine(PolicySettings(), PathGuard(ws, default_protected()))


ROUND3_DENY = [
    ("r3-pytest-override-var", "uv run pytest --override-ini=cache_dir=$O/c2",
     "confine:variable"),
    ("r3-pytest-override-outside", "uv run pytest --override-ini=cache_dir=../outside/k6",
     "confine:forbidden-option"),
    ("r3-pytest-override-dquote", 'uv run pytest --override-ini="cache_dir=../outside/w27"',
     "confine:forbidden-option"),
    ("r3-pytest-override-squote", "uv run pytest '--override-ini=cache_dir=../outside/w28'",
     "confine:forbidden-option"),
    ("r3-pytest-override-dotslash", "uv run pytest --override-ini=cache_dir=./../outside/w29",
     "confine:forbidden-option"),
    ("r3-pytest-override-linkdir", "uv run pytest --override-ini=cache_dir=linkdir/w31",
     "confine:forbidden-option"),
    ("r3-pytest-override-logfile", "uv run pytest --override-ini=log_file=$O/w35",
     "confine:variable"),
    ("r3-pytest-override-addopts",
     "uv run pytest --override-ini=addopts=--junitxml=../outside/w36.xml",
     "confine:forbidden-option"),
    ("r3-ruff-config-var", "uv run ruff check --config 'cache-dir=\"$O/rc\"' .",
     "confine:forbidden-option"),
    ("r3-ruff-config-outside", "uv run ruff check --config 'cache-dir=\"../outside/rc2\"' .",
     "confine:forbidden-option"),
    ("r3-ruff-config-spaces", "uv run ruff check --config 'cache-dir = \"../outside/w40\"' .",
     "confine:forbidden-option"),
    ("r3-ruff-config-eq", "uv run ruff check --config='cache-dir=\"../outside/w41\"' .",
     "confine:forbidden-option"),
    ("r3-ruff-config-squote", "uv run ruff check --config \"cache-dir='../outside/w42'\" .",
     "confine:forbidden-option"),
    ("r3-ruff-format-config", "uv run ruff format --config 'cache-dir=\"../outside/w44\"' .",
     "confine:forbidden-option"),
    ("r3-pytest-override-pkgdata", f"uv run pytest --override-ini=cache_dir={PKG_DATA}",
     "confine:forbidden-option"),
    ("r3-pytest-override-e2e", f"uv run pytest --override-ini=cache_dir={PKG_E2E}",
     "confine:forbidden-option"),
    ("r3-pytest-override-git", "uv run pytest --override-ini=cache_dir=.git",
     "confine:forbidden-option"),
    ("r3-pytest-override-git-hooks", "uv run pytest --override-ini=cache_dir=.git/hooks",
     "confine:forbidden-option"),
    ("r3-pytest-override-cora", "uv run pytest --override-ini=cache_dir=.cora",
     "confine:forbidden-option"),
    ("r3-ruff-config-git-hooks", "uv run ruff check --config 'cache-dir=\".git/hooks\"' .",
     "confine:forbidden-option"),
    ("r3-echo-root-glob", "echo /*", "floor:outside-workspace"),
    ("r3-echo-users-glob", "echo /Users/*", "floor:outside-workspace"),
    ("r3-echo-users-ssh", "echo /Users/*/.ssh/*", "floor:outside-workspace"),
    ("r3-echo-parent-glob", "echo ../*", "floor:outside-workspace"),
    ("r3-echo-pwd-parent", "echo $PWD/../*", "floor:outside-workspace"),
    ("r3-echo-outside-glob", "echo ../outside/*", "floor:outside-workspace"),
    ("r3-echo-git-glob", "echo .git/*", "floor:protected-path"),
    ("r3-echo-n-var", "echo -n $O/*", "confine:variable"),
    ("r3-echo-e-var", "echo -e $O/*", "confine:variable"),
    ("r3-pytest-rootdir-git", "pytest --rootdir=.git", "floor:protected-write"),
    ("r3-pytest-rootdir-cora", "pytest --rootdir=.cora", "floor:protected-write"),
    ("r3-uv-pytest-rootdir-git", "uv run pytest --rootdir=.git", "floor:protected-write"),
]

ADVERSARIAL_DENY = [
    ("uv-with", "uv run --with x pytest", "confine:uv-run"),
    ("uv-directory", "uv run --directory /x pytest", "confine:uv-run"),
    ("uv-double-dash", "uv run -- pytest", "confine:uv-run"),
    ("uv-pytest-dash-override", "uv run pytest -- --override-ini=cache_dir=x",
     "confine:unknown-option"),
    ("uv-python-c", 'uv run python -c "print(1)"', "confine:uv-run"),
    ("uv-python3-c", "uv run python3 -c 'import os'", "confine:uv-run"),
    ("uv-env", "uv run env FOO=1 pytest", "confine:uv-run"),
    ("uv-bash", "uv run bash", "confine:uv-run"),
    ("uv-sh-c", "uv run sh -c id", "confine:uv-run"),
    ("uv-frozen", "uv run --frozen pytest", "confine:uv-run"),
    ("uv-no-project", "uv run --no-project pytest", "confine:uv-run"),
    ("uv-python-opt", "uv run --python 3.12 pytest", "confine:uv-run"),
    ("uv-env-file", "uv run --env-file .env pytest", "confine:uv-run"),
    ("uv-project-parent", "uv run --project .. pytest", "confine:uv-run"),
    ("uv-isolated", "uv run --isolated pytest", "confine:uv-run"),
    ("uv-offline", "uv run --offline pytest", "confine:uv-run"),
    ("uv-git-push", "uv run git push origin main", "confine:uv-run"),
    ("uv-curl", "uv run curl https://example.com", "confine:uv-run"),
    ("uv-python-http", "uv run python -m http.server", "confine:uv-run"),
    ("uv-abs-pytest", "uv run /bin/pytest", "confine:uv-run"),
    ("uv-python-module-pytest-override", "uv run python -m pytest --override-ini=cache_dir=x",
     "confine:forbidden-option"),
    ("uv-python-module-rootdir", "uv run python -m pytest --rootdir=.git",
     "floor:protected-write"),
    ("uv-script-outside", "uv run python ../outside/x.py", "floor:outside-workspace"),
    ("uv-script-not-py", "uv run python ../outside/secret.txt", "confine:uv-run"),
    ("uv-pytest-p-plugin", "uv run pytest -p myplugin", "confine:forbidden-option"),
    ("uv-ruff-format-config", "uv run ruff format --config x .", "confine:forbidden-option"),
    ("uv-rootdir-cora", "uv run pytest --rootdir=.cora", "floor:protected-write"),
    ("uv-rootdir-outside", "uv run pytest --rootdir=../outside", "floor:outside-workspace"),
    ("uv-stdbuf-bash", "stdbuf -oL uv run bash", "confine:uv-run"),
    ("uv-command-prefix", "command uv run --with x pytest", "confine:uv-run"),
    ("uv-exec-prefix", "exec uv run --with x pytest", "confine:uv-run"),
    ("uv-env-prefix", "env uv run --with x pytest", "confine:uv-run"),
    ("uv-nohup-dash", "nohup uv run -- pytest", "confine:uv-run"),
    ("uv-sudo", "sudo uv run pytest", "floor:privilege"),
    ("uv-xargs", "xargs uv run pytest", "confine:xargs"),
    ("echo-braces", "echo {.git,x}", "confine:brace"),
    ("echo-tilde", "echo ~", "confine:tilde"),
    ("echo-tilde-ssh", "echo ~/.ssh", "confine:tilde"),
    ("echo-env-glob", "echo .env*", "floor:credential-file"),
    ("echo-bracket-git", "echo .[g]it/config", "floor:protected-path"),
    ("echo-home-var", "echo $HOME", "confine:variable"),
    ("echo-etc", "echo /etc/passwd", "floor:outside-workspace"),
    ("echo-dotdot-collapse", "echo a/../../outside", "floor:outside-workspace"),
    ("echo-dotdot-only", "echo ..", "floor:outside-workspace"),
    ("echo-n-outside", "echo -n ../outside/secret.txt", "floor:outside-workspace"),
    ("echo-e-outside-glob", "echo -e ../*", "floor:outside-workspace"),
    ("echo-E-git", "echo -E .git/*", "floor:protected-path"),
    ("echo-question-glob", "echo ../o?tside/*", "floor:outside-workspace"),
    ("echo-redirect-outside", "echo hi > ../outside/x", "floor:outside-workspace"),
    ("echo-operand-colon", "echo x:../outside/secret.txt", "floor:outside-workspace"),
    ("head-numeric-outside", "head -20 ../outside/secret.txt", "floor:outside-workspace"),
    ("tail-numeric-outside", "tail -20 ../outside/secret.txt", "floor:outside-workspace"),
    ("head-n-outside", "head -n ../outside/secret.txt", "floor:outside-workspace"),
    ("head-c-outside", "head -c 1 ../outside/secret.txt", "floor:outside-workspace"),
    ("tail-F-outside", "tail -F ../outside/x", "floor:outside-workspace"),
    ("head-numeric-git", "head -5 .git/config", "floor:protected-path"),
    ("head-numeric-env", "head -2 .env", "floor:credential-file"),
    ("tail-n-git", "tail -n5 .git/config", "floor:protected-path"),
    ("head-dashdash-outside", "head -3 -- ../x", "floor:outside-workspace"),
    ("head-after-flags-outside", "head -n 5 -c 2 ../x", "floor:outside-workspace"),
    ("head-bad-cluster", "head -20x ../outside", "floor:outside-workspace"),
    ("pipe-head-outside-operand", "cat README.md | head ../outside/secret.txt",
     "floor:outside-workspace"),
    ("pipe-head-n-outside", "cat README.md | head -n ../outside", "floor:outside-workspace"),
    ("pipe-tail-c-outside", "echo hi | tail -c ../outside/x", "floor:outside-workspace"),
    ("pipe-grep-head-outside", "grep x README.md | head -5 ../outside/x",
     "floor:outside-workspace"),
    ("pipe-source-outside", "cat ../outside/secret.txt | head -20", "floor:outside-workspace"),
    ("pipe-git-cat-outside", "git diff | cat ../outside/secret.txt",
     "floor:outside-workspace"),
    ("pipe-git-sh", "git diff | sh", "floor:pipe-exec"),
    ("pipe-cat-python", "cat README.md | python", "floor:pipe-exec"),
    ("pipe-head-redirect-outside", "echo x | head -20 > ../outside/out",
     "floor:outside-workspace"),
    ("pipe-wc-outside", "ls | wc -l ../outside", "floor:outside-workspace"),
    ("rootdir-confcut-git", "pytest --confcutdir=.git", "floor:protected-write"),
    ("rootdir-confcut-cora", "pytest --confcutdir=.cora", "floor:protected-write"),
    ("rootdir-confcut-outside", "pytest --confcutdir=../outside", "floor:outside-workspace"),
    ("rootdir-space-git", "pytest --rootdir .git tests", "floor:protected-write"),
    ("rootdir-etc", "pytest --rootdir=/etc", "floor:outside-workspace"),
    ("pytest-p-plugin-after-allowed", "pytest -p no:cacheprovider -p myplugin",
     "confine:forbidden-option"),
    ("pytest-p-near-miss", "pytest -p no:cacheprovider2", "confine:forbidden-option"),
    ("pytest-p-attached-near-miss", "pytest -pno:randomlyx", "confine:forbidden-option"),
    ("pytest-cache-show-outside", "pytest --cache-show=../outside", "floor:outside-workspace"),
    ("pytest-cache-clear-value", "pytest --cache-clear=x", "confine:unknown-option"),
    ("pytest-version-value", "pytest --version=x", "confine:unknown-option"),
    ("pytest-cov", "pytest --cov=src", "confine:unknown-option"),
    ("pytest-cov-report", "pytest --cov-report=html", "confine:unknown-option"),
    ("pytest-junit-git", "pytest --junitxml=.git/x.xml", "floor:protected-write"),
    ("time-bash-c", "time bash -c id", "confine:shell-c"),
    ("nice-sh-c", "nice -n 5 sh -c id", "confine:shell-c"),
    ("timeout-sh-c", "timeout 5 sh -c id", "confine:shell-c"),
    ("bare-head-unpiped", "head", "default"),
    ("bare-tail-unpiped", "tail", "default"),
]

ALLOW = [
    "head -20 README.md",
    "tail -20 README.md",
    "head -n20 README.md",
    "tail -F README.md",
    "head -5 README.md src/app.py",
    "cat README.md | head -20",
    "cat README.md | tail",
    "grep hello README.md | head -5",
    "git diff | head -50",
    "ls src | head",
    "git log | head -5",
    "cat README.md | wc -l",
    "echo done | head -3",
    "echo hello",
    'echo "done"',
    "echo a/b",
    "echo src/app.py",
    "pytest --version",
    "ruff --version",
    "uv run pytest --version",
    "uv run ruff --version",
    "pytest -p no:cacheprovider",
    "pytest -pno:cacheprovider",
    "pytest -p no:randomly tests",
    "pytest --cache-show",
    "pytest --cache-clear",
    "pytest --rootdir=.",
    "pytest --confcutdir=tests",
    "uv run pytest -q tests",
    "uv run ruff check .",
    "python script.py | head -20",
]

CONFINE_ALLOW = [
    "uv run python script.py",
    "uv run python -m pytest tests/",
    "uv run python -m ruff check .",
    "uv run pytest -q tests",
    "uv run ruff check src",
    "head -20 README.md",
    "tail -n 20 README.md",
    "git diff | head -50",
    "cat README.md | tail",
]

@pytest.mark.parametrize("case", ROUND3_DENY, ids=[c[0] for c in ROUND3_DENY])
def test_round3_denied(box, case):
    _, command, rule = case
    verdict = box.evaluate("run_shell", {"command": command})
    assert verdict.decision == "deny", verdict
    assert verdict.rule == rule


@pytest.mark.parametrize("case", ADVERSARIAL_DENY, ids=[c[0] for c in ADVERSARIAL_DENY])
def test_adversarial_coverage_denied(box, case):
    _, command, rule = case
    verdict = box.evaluate("run_shell", {"command": command})
    assert verdict.decision == "deny", verdict
    assert verdict.rule == rule


@pytest.mark.parametrize("command", ALLOW)
def test_coverage_allowed(box, command):
    verdict = box.evaluate("run_shell", {"command": command})
    assert verdict.decision == "allow", verdict


@pytest.mark.parametrize("command", CONFINE_ALLOW)
def test_coverage_confinement_allowed(box, command):
    verdict = box.confine(command)
    assert verdict.decision == "allow", verdict


def test_pipe_sink_respects_user_deny(box):
    rule = Rule("user-no-head", "deny", ("run_shell",), commands=("head *",), index=1)
    engine = PolicyEngine(PolicySettings(rules=(rule,)), box.guard)
    verdict = engine.evaluate("run_shell", {"command": "cat README.md | head"})
    assert verdict.decision == "deny", verdict
    assert verdict.rule == "user-no-head"


UNTABLED_ALLOW = frozenset({
    "python -m unittest", "python -m unittest *", "python3 -m unittest",
    "python3 -m unittest *",
    "npm test", "cargo test", "go test ./...", "make test",
})


def _patterns() -> list[str]:
    toolchain = {p for tc in TOOLCHAINS.values() for p in (*tc.commands, *tc.file_runs)}
    return sorted(set(SHELL_ALLOW) | toolchain)


@pytest.mark.parametrize("pattern", _patterns())
def test_every_default_allow_pattern_has_table_coverage(pattern):
    argv = shlex.split(pattern.replace("*", "x"))
    key = shellguard.table_key(argv)
    if pattern in UNTABLED_ALLOW:
        assert key is None, pattern
        return
    assert key is not None, pattern
    assert key in PROGRAM_SPECS or key == "python script" or key.startswith("git "), pattern


def test_uv_run_patterns_redispatch_into_tables():
    assert shellguard.table_key(["uv", "run", "pytest", "x"]) == "pytest"
    assert shellguard.table_key(["uv", "run", "ruff", "check"]) == "ruff"
    assert shellguard.table_key(["uv", "run", "--with", "x", "pytest"]) is None
    assert shellguard.table_key(["uv", "run", "python", "-c", "1"]) is None


def test_search_skips_dangling_symlink(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("hello\n", encoding="utf-8")
    (ws / "dangling").symlink_to(ws / "missing.txt")
    ctx = ToolContext(Workspace(ws), ApprovalPolicy("ask"))
    result = asyncio.run(SearchTool().run({"pattern": "hello", "path": "."}, ctx))
    assert result.ok
    assert "README.md:1: hello" in result.output
