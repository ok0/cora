from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider
from cora.bench import e2e
from cora.bench.e2e import load_e2e_tasks, select_e2e_tasks
from cora.cli.main import app
from cora.core.errors import ConfigError
from e2e_util import GRADER_OK, make_task

SAMPLE_IDS = [
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
]
FORBIDDEN_NET = (
    "socket", "ssl", "urllib", "http.client", "httpx", "requests", "ftplib", "smtplib",
    "telnetlib", "xmlrpc",
)


def test_samples_load() -> None:
    tasks = load_e2e_tasks()
    ids = [t.id for t in tasks]
    assert ids[:5] == SAMPLE_IDS
    assert [t.difficulty for t in tasks[:5]] == ["easy", "easy", "medium", "medium", "hard"]
    assert ids[5:13] == [
        "e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06",
        "e2e_hx1", "e2e_hx2",
    ]
    assert all(i.startswith("e2e_n") for i in ids[13:])
    for t in tasks:
        assert not t.reference_dir.resolve().is_relative_to(t.template_dir.resolve())
        assert t.grader_visibility == "hidden"


@pytest.mark.parametrize(
    ("label", "overrides", "problem"),
    [
        ("e2e_case", {"title": None}, "missing required field 'title'"),
        ("e2e_case", {"limits.wall_s": 0}, "limits.wall_s must be > 0"),
        ("e2e_case", {"limits.cost_usd": -1}, "limits.cost_usd must be > 0"),
        ("e2e_case", {"limits.max_iterations": 0}, "limits.max_iterations must be > 0"),
        ("bad", {"id": "bad"}, "id must start with 'e2e_'"),
    ],
)
def test_invalid_tasks(
    tmp_path: Path, label: str, overrides: dict, problem: str
) -> None:
    make_task(tmp_path, "e2e_case", GRADER_OK, **overrides)
    expected = re.escape(f"e2e task '{label}': {problem}")
    with pytest.raises(ConfigError, match=expected):
        load_e2e_tasks(tmp_path)


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    make_task(tmp_path, "e2e_aa", GRADER_OK, id="e2e_same")
    make_task(tmp_path, "e2e_bb", GRADER_OK, id="e2e_same")
    with pytest.raises(ConfigError, match="duplicate e2e task id"):
        load_e2e_tasks(tmp_path)


def test_grader_entry_missing_rejected(tmp_path: Path) -> None:
    task_dir = make_task(tmp_path, "e2e_case", GRADER_OK)
    (task_dir / "grader" / "grade.py").unlink()
    with pytest.raises(ConfigError, match="grader entry not found"):
        load_e2e_tasks(tmp_path)


def test_grader_dir_missing_rejected(tmp_path: Path) -> None:
    task_dir = make_task(tmp_path, "e2e_case", GRADER_OK)
    shutil.rmtree(task_dir / "grader")
    with pytest.raises(ConfigError, match="grader directory not found"):
        load_e2e_tasks(tmp_path)


def test_reference_inside_template_rejected(tmp_path: Path) -> None:
    task_dir = make_task(tmp_path, "e2e_case", GRADER_OK, **{"reference.dir": "template/ref"})
    (task_dir / "template" / "ref").mkdir()
    with pytest.raises(ConfigError, match="reference solution is inside the agent template"):
        load_e2e_tasks(tmp_path)


def test_select_unknown_e2e_id() -> None:
    with pytest.raises(ConfigError, match="unknown e2e task id"):
        select_e2e_tasks(["nope"])


def test_graders_use_no_network() -> None:
    for task in load_e2e_tasks():
        for path in sorted(task.grader_dir.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    assert not name.startswith(FORBIDDEN_NET), f"{path}: imports {name}"


def test_grader_env_whitelist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-1234567890")
    monkeypatch.setenv("HTTPS_PROXY", "http://x")
    env = e2e.grader_env(tmp_path)
    assert "OPENROUTER_API_KEY" not in env
    assert "HTTPS_PROXY" not in env
    assert env["PYTHONHASHSEED"] == "0"
    assert env["HOME"] == str(tmp_path)


def test_plan_suite_e2e(tmp_path: Path, cfg_file: Path, no_network: list[str]) -> None:
    result = CliRunner().invoke(
        app,
        ["bench", "plan", "--suite", "e2e", "--tasks", ",".join(SAMPLE_IDS),
         "--repeats", "3", "--models", "mock/cheap", "--protocols", "react",
         "-c", str(cfg_file), "-w", str(tmp_path)],
    )
    assert result.exit_code == 0, result.stderr
    for tid in SAMPLE_IDS:
        assert f"| {tid} |" in result.stdout
    row = "| - | mock/cheap | react | e2e_todo_cli | 3 | 20 | 0.030000 | 0.030000 |"
    assert row in result.stdout
    assert "total_max_usd: 0.570000" in result.stdout
    assert "OVER CAP" in result.stdout
    assert "suggested --repeats: 1" in result.stdout
    assert ScriptedProvider.calls == []
    ab = CliRunner().invoke(
        app,
        ["bench", "plan", "--suite", "e2e", "--tasks", ",".join(SAMPLE_IDS),
         "--repeats", "3", "--models", "mock/cheap", "--protocols", "react",
         "--ab", "deleg-off,strong-only", "-c", str(cfg_file), "-w", str(tmp_path)],
    )
    assert ab.exit_code == 0, ab.stderr
    assert "| strong-only |" in ab.stdout


def test_suite_invalid_value(cfg_file: Path, tmp_path: Path) -> None:
    bad = CliRunner().invoke(
        app, ["bench", "--live", "--suite", "x", "-c", str(cfg_file), "-w", str(tmp_path)]
    )
    assert bad.exit_code == 2
    offline = CliRunner().invoke(app, ["bench", "--suite", "e2e"])
    assert offline.exit_code == 2
    assert "require --live" in offline.stderr
