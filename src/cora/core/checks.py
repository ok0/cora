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
from cora.core.toolchains import PYTEST_COMMAND as PYTEST_COMMAND
from cora.core.toolchains import TOOLCHAINS, Marker
from cora.core.tools.base import IGNORED_DIRS

SELFTEST_DIR = ".cora/selftest"
SELFTEST_COMMAND = "python -m pytest -q .cora/selftest"
TEST_NAME_PATTERNS = ("test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*")
MAX_SNAPSHOT_FILES = 5000
MAX_READ_BYTES = 1_000_000


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


def _is_regular_root_file(root: Path, guard: PathGuard, name: str) -> bool:
    path = root / name
    if path.is_symlink() or not path.is_file():
        return False
    return guard.check_real(Path(os.path.realpath(path)), write=False) is None


def _toml_has(root: Path, guard: PathGuard, name: str, key: str) -> bool:
    text = _read(root, guard, name)
    if text is None:
        return False
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    return key in data.get("tool", {})


def _json_script(root: Path, guard: PathGuard, name: str, script: str, placeholder: str) -> bool:
    text = _read(root, guard, name)
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
    value = scripts.get(script)
    return isinstance(value, str) and bool(value) and placeholder not in value


def _has_target(root: Path, guard: PathGuard, name: str, target: str) -> bool:
    text = _read(root, guard, name)
    return text is not None and re.search(
        rf"^{re.escape(target)}\s*:(?!=)", text, re.M) is not None


def _marker_present(root: Path, guard: PathGuard, marker: Marker) -> bool:
    for d in marker.dirs:
        path = root / d
        if path.is_dir() and not path.is_symlink() and guard.check_real(
                Path(os.path.realpath(path)), write=False) is None:
            return True
    if any(_is_regular_root_file(root, guard, f) for f in marker.files):
        return True
    if marker.names:
        for rel in _walk(root, guard, max_depth=2):
            name = rel.rsplit("/", 1)[-1]
            if any(fnmatch.fnmatchcase(name, pat) for pat in marker.names):
                return True
    if marker.toml_key and _toml_has(root, guard, *marker.toml_key):
        return True
    if marker.json_script and _json_script(root, guard, *marker.json_script):
        return True
    return bool(marker.target_rule) and _has_target(root, guard, *marker.target_rule)


def present_toolchains(workspace: Path) -> tuple[str, ...]:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    return tuple(
        tid for tid, tc in TOOLCHAINS.items()
        if _marker_present(root, guard, tc.check) or _marker_present(root, guard, tc.also))


def detect_check_command(workspace: Path) -> str | None:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    for tc in TOOLCHAINS.values():
        if _marker_present(root, guard, tc.check):
            return tc.check_command
    return None


def is_python_workspace(workspace: Path) -> bool:
    root = Path(os.path.realpath(workspace))
    guard = _guard(root)
    return _marker_present(root, guard, TOOLCHAINS["python"].also)


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
