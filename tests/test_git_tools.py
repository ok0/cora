from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest

from cora.core.config import ToolSettings
from cora.core.tools import ApprovalPolicy, ToolContext, ToolRegistry, Workspace, default_tools
from cora.core.tools.git import git_env

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

reg = ToolRegistry(default_tools())


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))


def _git(repo, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _exec(ctx, name, args):
    return asyncio.run(reg.execute(name, args, ctx))


def mk_ctx(path, policy, **limits):
    return ToolContext(Workspace(path), policy, limits=ToolSettings(**limits))


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", ".git/hooks")
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_read_tools_no_approval(repo):
    def boom(_):
        raise AssertionError("no approval expected")

    ctx = mk_ctx(repo, ApprovalPolicy("ask", ask=boom))
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    (repo / "b.txt").write_text("new\n", encoding="utf-8")
    res = _exec(ctx, "git_status", {})
    assert res.ok
    assert "## main" in res.output
    assert "a.txt" in res.output
    assert "b.txt" in res.output
    res = _exec(ctx, "git_diff", {})
    assert res.ok
    assert "+two" in res.output
    res = _exec(ctx, "git_diff", {"staged": True})
    assert res.ok
    assert "no changes" in res.output
    _git(repo, "add", "a.txt")
    res = _exec(ctx, "git_diff", {"staged": True})
    assert res.ok
    assert "+two" in res.output
    assert _exec(ctx, "git_diff", {"path": "a.txt"}).ok
    res = _exec(ctx, "git_log", {"count": 1})
    assert res.ok
    assert "init" in res.output
    assert len(res.output.strip().splitlines()) == 1


def test_large_diff_truncated(repo):
    (repo / "a.txt").write_text("".join(f"line {i}\n" for i in range(5000)), encoding="utf-8")
    ctx = mk_ctx(repo, ApprovalPolicy("auto"), git_max_output_chars=1000)
    out = _exec(ctx, "git_diff", {}).output
    assert "[truncated" in out
    assert len(out) <= 1100


def test_log_count_clamped(repo):
    for i in range(3):
        (repo / "a.txt").write_text(f"v{i}\n", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", f"c{i}")
    ctx = mk_ctx(repo, ApprovalPolicy("auto"), git_log_max_count=2)
    out = _exec(ctx, "git_log", {"count": 100}).output
    assert len(out.splitlines()) == 2


def test_commit_ask_shows_files_and_message(repo):
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    head = _git(repo, "rev-parse", "HEAD")
    reqs = []
    ctx = mk_ctx(repo, ApprovalPolicy("ask", review=lambda r: reqs.append(r) or "no"))
    res = _exec(ctx, "git_commit", {"message": "msg one"})
    assert not res.ok
    assert "denied by user" in res.output
    assert "a.txt" in reqs[0].detail
    assert "msg one" in reqs[0].detail
    assert _git(repo, "rev-parse", "HEAD") == head


def test_commit_approved_creates_commit(repo):
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    ctx = mk_ctx(repo, ApprovalPolicy("ask", review=lambda r: "yes"))
    res = _exec(ctx, "git_commit", {"message": "msg one"})
    assert res.ok
    assert res.output.startswith("ok: committed")
    assert _git(repo, "log", "-1", "--format=%s") == "msg one"
    assert _git(repo, "rev-list", "--count", "HEAD") == "2"


def test_add_deny_unchanged(repo):
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    ctx = mk_ctx(repo, ApprovalPolicy("deny"))
    res = _exec(ctx, "git_add", {"paths": ["a.txt"]})
    assert not res.ok
    assert "denied by user" in res.output
    assert _git(repo, "diff", "--cached", "--name-only") == ""


def test_commit_errors(repo):
    calls = []
    ctx = mk_ctx(repo, ApprovalPolicy("ask", review=lambda r: calls.append(r) or "yes"))
    res = _exec(ctx, "git_commit", {"message": "  "})
    assert not res.ok
    assert "must not be empty" in res.output
    assert calls == []
    res = _exec(ctx, "git_commit", {"message": "m"})
    assert not res.ok
    assert "nothing staged" in res.output
    assert calls == []


def test_branch_create_and_switch(repo):
    ctx = mk_ctx(repo, ApprovalPolicy("auto"))
    res = _exec(ctx, "git_branch", {"name": "feature/x", "create": True})
    assert res.ok
    assert _git(repo, "branch", "--show-current") == "feature/x"
    assert _exec(ctx, "git_branch", {"name": "main"}).ok


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("git_branch", {"name": "--force"}, "invalid arguments"),
        ("git_branch", {"name": "-D"}, "invalid arguments"),
        ("git_branch", {"name": "x", "delete": True}, "unsupported argument"),
        ("git_branch", {"name": "a..b"}, "invalid arguments"),
        ("git_add", {"paths": ["--no-verify"]}, "invalid arguments"),
        ("git_add", {"paths": ["-A"]}, "invalid arguments"),
        ("git_add", {"paths": ["../x"]}, "denied"),
        ("git_add", {"paths": ["/etc/passwd"]}, "invalid arguments"),
        ("git_add", {"paths": "a.txt"}, "invalid arguments"),
        ("git_commit", {"message": "m", "no_verify": True}, "unsupported argument"),
        ("git_commit", {"message": "m", "amend": True}, "unsupported argument"),
        ("git_diff", {"path": "-p"}, "invalid arguments"),
        ("git_diff", {"args": "--output=/tmp/x"}, "unsupported argument"),
        ("git_log", {"count": "--all"}, "invalid arguments"),
        ("git_status", {"porcelain": "--force"}, "unsupported argument"),
    ],
)
def test_rejected_arguments(repo, tool, args, expected):
    ctx = mk_ctx(repo, ApprovalPolicy("auto"))
    head = _git(repo, "rev-parse", "HEAD")
    res = _exec(ctx, tool, args)
    assert res.ok is False
    assert expected in res.output
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "branch", "--show-current") == "main"


def test_forbidden_tools_absent(tmp_path):
    names = set(reg.names())
    for forbidden in (
        "git_push",
        "git_pull",
        "git_fetch",
        "git_reset",
        "git_clean",
        "git_rebase",
        "git_config",
        "git_clone",
    ):
        assert forbidden not in names
    ctx = ToolContext(Workspace(tmp_path), ApprovalPolicy("auto"))
    res = _exec(ctx, "git_push", {})
    assert "unknown tool" in res.output


def test_shell_metacharacters_literal(repo):
    ctx = mk_ctx(repo, ApprovalPolicy("auto"))
    res = _exec(ctx, "git_add", {"paths": ["a.txt; touch pwned"]})
    assert res.ok is False
    assert not (repo / "pwned").exists()
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    res = _exec(ctx, "git_commit", {"message": "$(touch pwned2) --no-verify"})
    assert res.ok
    assert _git(repo, "log", "-1", "--format=%s") == "$(touch pwned2) --no-verify"
    assert not (repo / "pwned2").exists()


def test_not_a_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    ctx = mk_ctx(plain, ApprovalPolicy("auto"))
    res = _exec(ctx, "git_status", {})
    assert res.ok is False
    assert "not inside a git repository" in res.output
    res = _exec(ctx, "git_commit", {"message": "m"})
    assert res.ok is False
    assert "not inside a git repository" in res.output


def test_git_env_hides_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("GIT_DIR", "/tmp/evil")
    ctx = ToolContext(
        Workspace(tmp_path),
        ApprovalPolicy("auto"),
        hidden_env=frozenset({"OPENROUTER_API_KEY"}),
    )
    env = git_env(ctx)
    assert "OPENROUTER_API_KEY" not in env
    assert "GIT_DIR" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_not_a_repo_same_message_all_git_tools(tmp_path, monkeypatch):
    from cora.core.tools.git import NOT_A_REPO

    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.txt").write_text("x\n", encoding="utf-8")
    ctx = mk_ctx(plain, ApprovalPolicy("auto"))
    cases = [
        ("git_status", {}),
        ("git_diff", {}),
        ("git_diff", {"staged": True}),
        ("git_diff", {"path": "a.txt"}),
        ("git_log", {}),
        ("git_log", {"count": 3}),
        ("git_add", {"paths": ["a.txt"]}),
        ("git_commit", {"message": "m"}),
        ("git_branch", {"name": "feature"}),
    ]
    for name, args in cases:
        res = _exec(ctx, name, args)
        assert res.ok is False, name
        assert res.output == NOT_A_REPO, (name, res.output)
        low = res.output.lower()
        assert "usage" not in low and "--no-index" not in low and "fatal" not in low
