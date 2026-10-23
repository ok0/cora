from __future__ import annotations

import asyncio
import shutil
import subprocess

from cora.core.agent import Agent
from cora.core.project import draft_guide, load_project_context
from cora.core.tools import ApprovalPolicy


def test_guide_priority(tmp_path):
    (tmp_path / "CORA.md").write_text("cora", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude", encoding="utf-8")
    assert load_project_context(tmp_path).guide_path.name == "CORA.md"
    (tmp_path / "CORA.md").unlink()
    assert load_project_context(tmp_path).guide_path.name == "AGENTS.md"
    (tmp_path / "AGENTS.md").unlink()
    assert load_project_context(tmp_path).guide_path.name == "CLAUDE.md"


def test_no_guide_no_git_renders_empty(tmp_path):
    assert load_project_context(tmp_path).render() == ""


def test_guide_truncated(tmp_path):
    (tmp_path / "CORA.md").write_text("x" * 9000, encoding="utf-8")
    text = load_project_context(tmp_path).guide_text
    assert text.endswith("...[guide truncated]")


def test_git_status_summary(tmp_path):
    if shutil.which("git") is None:
        import pytest

        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    ctx = load_project_context(tmp_path)
    assert ctx.git_status.startswith("## ")
    assert "a.txt" in ctx.git_status
    assert "Git status at session start" in ctx.render()


def test_agent_injects_project_context(scripted, mock_config, tmp_path):
    scripted.script[:] = ["Final Answer: ok"]
    asyncio.run(
        Agent(
            mock_config,
            tmp_path,
            ApprovalPolicy("auto"),
            project_context="\n\nPROJECT-MARKER",
        ).run("hi")
    )
    assert "PROJECT-MARKER" in scripted.calls[0].messages[0].content


def test_draft_guide_python_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    draft = draft_guide(tmp_path)
    assert "Test: uv run pytest" in draft
    assert "Lint: uv run ruff check ." in draft
    assert "Detected: pyproject.toml" in draft
