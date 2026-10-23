from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path

from cora.core.shellguard import PathGuard, default_protected
from cora.core.tools.base import IGNORED_DIRS

PYTEST_COMMAND = "python -m pytest -q"
SELFTEST_DIR = ".cora/selftest"
SELFTEST_COMMAND = "python -m pytest -q .cora/selftest"
TEST_NAME_PATTERNS = ("test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*")
MAX_SNAPSHOT_FILES = 5000
MAX_READ_BYTES = 1_000_000
PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
_MAKE_TEST = re.compile(r"^test\s*:(?!=)", re.M)


def _guard(root: Path) -> PathGuard:
    return PathGuard(root, default_protected())


def _walk(root: Path, guard: PathGuard, max_depth: int | None = None) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        depth = len(current.relative_to(root).parts)
        if max_depth is not None and depth + 1 >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORED_DIRS
                and not (current / d).is_symlink()
                and guard.check_real(Path(os.path.realpath(current / d)), write=False) is None
            ]
        for name in filenames:
            full = current / name
            if full.is_symlink() or not full.is_file():
                continue
            if guard.check_real(Path(os.path.realpath(full)), write=False) is not None:
                continue
            rel = full.relative_to(root)
            if max_depth is not None and len(rel.parts) > max_depth:
                continue
            yield rel.as_posix()


def _read(root: Path, guard: PathGuard, name: str) -> str | None:
    real = Path(os.path.realpath(root / name))
    if guard.check_real(real, write=False) is not None or not real.is_file():
        return None
    return real.read_bytes()[:MAX_READ_BYTES].decode("utf-8", "replace")


def is_test_path(rel: str) -> bool:
    if rel.startswith(".cora/"):
        return False
    parts = rel.split("/")
    if "tests" in parts[:-1]:
        return True
    return any(fnmatch.fnmatchcase(parts[-1], pat) for pat in TEST_NAME_PATTERNS)


def _has_pytest(root: Path, guard: PathGuard) -> bool:
    tests = root / "tests"
    if tests.is_dir() and not tests.is_symlink() and guard.check_real(
            Path(os.path.realpath(tests)), write=False) is None:
        return True
    for rel in _walk(root, guard, max_depth=2):
        name = rel.rsplit("/", 1)[-1]
        if fnmatch.fnmatchcase(name, "test_*.py") or fnmatch.fnmatchcase(name, "*_test.py"):
            return True
    text = _read(root, guard, "pyproject.toml")
    if text is not None:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return False
        return "pytest" in data.get("tool", {})
    return False


def _has_npm_test(root: Path, guard: PathGuard) -> bool:
    text = _read(root, guard, "package.json")
    if text is None:
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    scripts = data.get("scripts")
    if not isinstance(scripts, dict):
        return False
    test = scripts.get("test")
    return isinstance(test, str) and bool(test) and "no test specified" not in test


def _is_regular_root_file(root: Path, guard: PathGuard, name: str) -> bool:
    path = root / name
    if path.is_symlink() or not path.is_file():
        return False
    return guard.check_real(Path(os.path.realpath(path)), write=False) is None


def detect_check_command(workspace: Path) -> str | None:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    if _has_pytest(root, guard):
        return PYTEST_COMMAND
    if _has_npm_test(root, guard):
        return "npm test"
    if _is_regular_root_file(root, guard, "Cargo.toml"):
        return "cargo test"
    if _is_regular_root_file(root, guard, "go.mod"):
        return "go test ./..."
    makefile = _read(root, guard, "Makefile")
    if makefile is not None and _MAKE_TEST.search(makefile):
        return "make test"
    return None


def is_python_workspace(workspace: Path) -> bool:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    if any(_is_regular_root_file(root, guard, name) for name in PYTHON_MARKERS):
        return True
    return any(rel.endswith(".py") for rel in _walk(root, guard, max_depth=2))


def snapshot_tests(workspace: Path) -> dict[str, str]:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    out: dict[str, str] = {}
    for rel in _walk(root, guard):
        if not is_test_path(rel):
            continue
        out[rel] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        if len(out) >= MAX_SNAPSHOT_FILES:
            break
    return out


def tampered_tests(workspace: Path, snapshot: Mapping[str, str]) -> list[str]:
    root = Path(os.path.realpath(workspace))
    changed: list[str] = []
    for rel, digest in snapshot.items():
        path = root / rel
        if not path.is_file() or path.is_symlink():
            changed.append(rel)
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(rel)
    return sorted(changed)
