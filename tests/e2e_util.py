from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import PY, act
from cora.bench import e2e
from cora.bench.e2e import E2ETask

MD_OLD = r"""    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)"""

PARTIAL: dict[str, tuple[str, str, str] | None] = {
    "e2e_todo_cli": (
        "todo.py",
        'if cmd in ("done", "remove") and len(args) == 1:',
        'if cmd == "done" and len(args) == 1:',
    ),
    "e2e_text_stats": ("textstats.py", "key=lambda kv: (-kv[1], kv[0])", "key=lambda kv: -kv[1]"),
    "e2e_rest_notes": ("app.py", "return 204, None", "return 200, None"),
    "e2e_md_to_html": ("md2html.py", MD_OLD, "    return text"),
    "e2e_refactor_inventory": None,
}
EXPECTED_PARTIAL_SCORE = {
    "e2e_todo_cli": 5 / 6,
    "e2e_text_stats": 5 / 6,
    "e2e_rest_notes": 5 / 6,
    "e2e_md_to_html": 7 / 8,
    "e2e_refactor_inventory": 4 / 5,
}
CHECK_COUNTS = {
    "e2e_todo_cli": 6,
    "e2e_text_stats": 6,
    "e2e_rest_notes": 6,
    "e2e_md_to_html": 8,
    "e2e_refactor_inventory": 5,
}
GRADER_OK = "import json\nprint(json.dumps({'checks': [{'name': 'ok', 'passed': True}]}))\n"


def materialize(task: E2ETask, variant: str, tmp: Path) -> Path:
    ws = e2e.prepare_workspace(task, tmp)
    if variant == "template":
        return ws
    if variant == "reference":
        e2e.apply_reference(task, ws)
        return ws
    spec = PARTIAL[task.id]
    e2e.apply_reference(task, ws, delete=spec is not None)
    if spec is not None:
        rel, old, new = spec
        path = ws / rel
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, rel
        path.write_text(text.replace(old, new), encoding="utf-8")
    return ws


def solve_script(task: E2ETask, variant: str = "reference") -> list[str]:
    if variant == "template":
        return ["Final Answer: done"]
    spec = PARTIAL[task.id] if variant == "partial" else None
    steps: list[str] = []
    for path in sorted(task.reference_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(task.reference_dir).as_posix()
        new_text = path.read_text(encoding="utf-8")
        if spec is not None and rel == spec[0]:
            assert new_text.count(spec[1]) == 1, rel
            new_text = new_text.replace(spec[1], spec[2])
        template_path = task.template_dir / rel
        old = template_path.read_text(encoding="utf-8") if template_path.is_file() else ""
        steps.append(act("edit_file", {"path": rel, "old": old, "new": new_text}))
    if variant == "reference" or (variant == "partial" and spec is not None):
        for rel in task.reference_delete:
            command = f"{PY} -c \"import os; os.remove('{rel}')\""
            steps.append(act("run_shell", {"command": command}))
    steps.append("Final Answer: done")
    return steps


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _render_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    for key, table in tables:
        lines.append("")
        lines.append(f"[{key}]")
        for sub_key, sub_value in table.items():
            lines.append(f"{sub_key} = {_toml_value(sub_value)}")
    return "\n".join(lines) + "\n"


def _set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    if value is None:
        cur.pop(parts[-1], None)
    else:
        cur[parts[-1]] = value


def make_task(
    root: Path, tid: str, grader_code: str, timeout_s: float = 5, **toml_overrides: Any
) -> Path:
    task_dir = root / tid
    (task_dir / "template").mkdir(parents=True)
    (task_dir / "grader").mkdir()
    (task_dir / "reference").mkdir()
    (task_dir / "template" / "README.txt").write_text("template\n", encoding="utf-8")
    (task_dir / "REQUIREMENTS.md").write_text("# Requirements\n", encoding="utf-8")
    (task_dir / "grader" / "grade.py").write_text(grader_code, encoding="utf-8")
    (task_dir / "reference" / "README.txt").write_text("reference\n", encoding="utf-8")
    data: dict[str, Any] = {
        "id": tid,
        "title": "Synthetic task",
        "difficulty": "easy",
        "requirements": "REQUIREMENTS.md",
        "template": "template",
        "required_files": ["README.txt"],
        "limits": {"wall_s": 30, "cost_usd": 0.03, "max_iterations": 5},
        "grader": {"dir": "grader", "entry": "grade.py", "timeout_s": timeout_s},
        "reference": {"dir": "reference", "delete": []},
    }
    for dotted, value in toml_overrides.items():
        _set_path(data, dotted, value)
    (task_dir / "task.toml").write_text(_render_toml(data), encoding="utf-8")
    return task_dir
