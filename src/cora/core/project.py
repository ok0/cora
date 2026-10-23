from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

GUIDE_FILES = ("CORA.md", "AGENTS.md", "CLAUDE.md")
MAX_GUIDE_CHARS = 8000
MAX_GIT_LINES = 30
GIT_TIMEOUT_S = 5


@dataclass(frozen=True)
class ProjectContext:
    guide_path: Path | None = None
    guide_text: str = ""
    git_status: str | None = None

    def render(self) -> str:
        out = ""
        if self.guide_path is not None:
            out += f"\n\nProject guide ({self.guide_path.name}); follow it:\n{self.guide_text}"
        if self.git_status is not None:
            out += (
                "\n\nGit status at session start (git status --short --branch):\n"
                f"{self.git_status}"
            )
        return out


def git_output(workdir: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(workdir), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\n")


def is_git_repo(workdir: Path) -> bool:
    return git_output(workdir, ["rev-parse", "--is-inside-work-tree"]) == "true"


def find_guide(workdir: Path) -> Path | None:
    for name in GUIDE_FILES:
        if (workdir / name).is_file():
            return workdir / name
    return None


def load_project_context(workdir: Path) -> ProjectContext:
    guide_path = find_guide(workdir)
    guide_text = ""
    if guide_path is not None:
        guide_text = guide_path.read_text(encoding="utf-8", errors="replace")
        if len(guide_text) > MAX_GUIDE_CHARS:
            guide_text = guide_text[:MAX_GUIDE_CHARS] + "\n...[guide truncated]"
    git_status: str | None = None
    if is_git_repo(workdir):
        out = git_output(workdir, ["status", "--short", "--branch"])
        if out is not None:
            lines = out.splitlines()
            kept = lines[:MAX_GIT_LINES]
            extra = len(lines) - len(kept)
            if extra > 0:
                kept.append(f"... ({extra} more)")
            git_status = "\n".join(kept)
    return ProjectContext(guide_path, guide_text, git_status)


def draft_guide(workdir: Path) -> str:
    detected = [
        name
        for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Makefile")
        if (workdir / name).is_file()
    ]
    if "pyproject.toml" in detected:
        text = (workdir / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        uv = (workdir / "uv.lock").is_file()
        commands = (
            "uv sync" if uv else "pip install -e .",
            "uv run pytest" if uv else "pytest",
            "uv run ruff check ." if "ruff" in text else "TODO",
        )
    elif "package.json" in detected:
        commands = ("npm run build", "npm test", "npm run lint")
    elif "Cargo.toml" in detected:
        commands = ("cargo build", "cargo test", "cargo clippy")
    elif "go.mod" in detected:
        commands = ("go build ./...", "go test ./...", "go vet ./...")
    elif "Makefile" in detected:
        commands = ("make", "make test", "TODO")
    else:
        commands = ("TODO", "TODO", "TODO")
    build, test, lint = commands
    return (
        "# CORA.md\n"
        "\n"
        "Project guide for CORA and other coding agents. "
        "Keep it short; list only verifiable rules.\n"
        "\n"
        "## Project\n"
        f"- Root: {workdir.name}\n"
        f"- Detected: {', '.join(detected) or 'none'}\n"
        "\n"
        "## Commands\n"
        f"- Build: {build}\n"
        f"- Test: {test}\n"
        f"- Lint: {lint}\n"
        "\n"
        "## Rules\n"
        "- TODO: add rules learned from failures (with date).\n"
    )
