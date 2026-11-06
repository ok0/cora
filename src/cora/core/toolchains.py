"""Toolchain table: workspace markers and the shell allow patterns they enable (data only)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

PYTEST_COMMAND = "python -m pytest -q"


@dataclass(frozen=True)
class Marker:
    """The marker is present when any field matches.

    dirs: root directories that are not symlinks.
    files: regular root files that are not symlinks.
    names: file-name globs at depth <= 2.
    toml_key: (root file, key) where the file parses and key in data["tool"].
    json_script: (root file, script, placeholder) where scripts.<script> is a non-empty
        string that does not contain the placeholder.
    target_rule: (root file, target) where some line matches ^<target>\\s*: not followed by =.
    """

    dirs: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    toml_key: tuple[str, str] | None = None
    json_script: tuple[str, str, str] | None = None
    target_rule: tuple[str, str] | None = None


@dataclass(frozen=True)
class Toolchain:
    """check decides detect_check_command; check OR also enables commands (listed before the
    neutral set) and file_runs (listed after it); the split keeps today's rendered order."""

    check: Marker
    check_command: str
    commands: tuple[str, ...]
    file_runs: tuple[str, ...] = ()
    also: Marker = Marker()


TOOLCHAINS: Mapping[str, Toolchain] = MappingProxyType({
    "python": Toolchain(
        check=Marker(dirs=("tests",), names=("test_*.py", "*_test.py"),
                     toml_key=("pyproject.toml", "pytest")),
        check_command=PYTEST_COMMAND,
        commands=(
            "pytest", "pytest *", "python -m pytest", "python -m pytest *", "python3 -m pytest",
            "python3 -m pytest *", "python -m unittest", "python -m unittest *",
            "python3 -m unittest", "python3 -m unittest *", "uv run pytest", "uv run pytest *",
            "uv run ruff *", "ruff", "ruff *", "python -m ruff *", "python3 -m ruff *",
        ),
        file_runs=("python *.py", "python *.py *", "python3 *.py", "python3 *.py *"),
        also=Marker(files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
                    names=("*.py",)),
    ),
    "node": Toolchain(
        check=Marker(json_script=("package.json", "test", "no test specified")),
        check_command="npm test",
        commands=("npm test",),
    ),
    "rust": Toolchain(
        check=Marker(files=("Cargo.toml",)),
        check_command="cargo test",
        commands=("cargo test",),
    ),
    "go": Toolchain(
        check=Marker(files=("go.mod",)),
        check_command="go test ./...",
        commands=("go test ./...",),
    ),
    "make": Toolchain(
        check=Marker(target_rule=("Makefile", "test")),
        check_command="make test",
        commands=("make test",),
    ),
})
