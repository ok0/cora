from __future__ import annotations

import ast
import importlib.util
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
CORE = SRC / "cora" / "core"
FORBIDDEN = ("cora.cli", "cora.bench", "typer", "click", "prompt_toolkit", "rich")


def _imported_names(path: Path) -> list[tuple[int, str]]:
    package = ".".join(path.relative_to(SRC).parent.parts)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                name = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
            else:
                name = node.module or ""
            found.append((node.lineno, name))
    return found


def test_no_new_runtime_dependencies():
    data = tomllib.loads((SRC.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == [
        "httpx>=0.27", "typer>=0.16", "prompt_toolkit>=3.0.50", "rich>=13.7"]


def test_core_does_not_import_cli_bench_or_adapters():
    violations: list[str] = []
    for path in sorted(CORE.rglob("*.py")):
        for lineno, name in _imported_names(path):
            if name.startswith(FORBIDDEN):
                violations.append(f"{path}:{lineno} imports {name}")
    assert not violations, "\n".join(violations)
