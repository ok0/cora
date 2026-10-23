from __future__ import annotations

import json
import subprocess
import sys
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

import cora.cli.main as main
from cora.cli.main import BENCH_MISSING, app
from cora.core import shellguard


@pytest.fixture
def no_bench(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(sys.modules):
        if key == "cora.bench" or key.startswith("cora.bench."):
            monkeypatch.setitem(sys.modules, key, None)
    monkeypatch.setitem(sys.modules, "cora.bench", None)


def test_non_bench_commands_work_without_bench(no_bench, scripted, ws, cfg_file) -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0

    scripted.script[:] = ["Final Answer: 42"]
    result = CliRunner().invoke(
        app, ["run", "x", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"]
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "42"
    assert not isinstance(result.exception, ImportError)

    scripted.script[:] = ["Final Answer: 42"]
    result = CliRunner().invoke(
        app, ["run", "x", "--headless", "--json", "-w", str(ws), "-c", str(cfg_file)]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True
    assert not isinstance(result.exception, ImportError)

    result = CliRunner().invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    assert not isinstance(result.exception, ImportError)


@pytest.mark.parametrize(
    "args",
    [
        ["bench"],
        ["bench", "plan"],
        ["bench", "compare", "report.json"],
        ["decider", "eval"],
        ["sale", "eval"],
    ],
)
def test_bench_commands_print_message_without_bench(no_bench, args) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert result.stderr == BENCH_MISSING + "\n"
    assert result.stdout == ""
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, ImportError)


@pytest.mark.parametrize(
    "args",
    [
        ["bench", "--help"],
        ["bench", "plan", "--help"],
        ["bench", "compare", "--help"],
        ["decider", "--help"],
        ["sale", "--help"],
    ],
)
def test_bench_help_without_bench(no_bench, args) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0
    assert BENCH_MISSING not in result.output


def test_broken_bench_submodule_is_not_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "cora.bench.plan", None)
    result = CliRunner().invoke(app, ["bench", "plan"])
    assert isinstance(result.exception, ModuleNotFoundError)
    assert result.exit_code != 2
    assert BENCH_MISSING not in result.stderr


def test_require_bench_only_maps_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def raiser(exc: BaseException):
        def import_module(name: str) -> None:
            raise exc

        return import_module

    monkeypatch.setattr(
        main,
        "importlib",
        SimpleNamespace(
            import_module=raiser(ModuleNotFoundError("No module named 'yaml'", name="yaml"))
        ),
    )
    with pytest.raises(ModuleNotFoundError):
        main._require_bench()

    monkeypatch.setattr(
        main,
        "importlib",
        SimpleNamespace(import_module=raiser(ImportError("cannot import name 'x'"))),
    )
    with pytest.raises(ImportError):
        main._require_bench()

    monkeypatch.setattr(
        main,
        "importlib",
        SimpleNamespace(
            import_module=raiser(
                ModuleNotFoundError("No module named 'cora.bench'", name="cora.bench")
            )
        ),
    )
    with pytest.raises(typer.Exit) as excinfo:
        main._require_bench()
    assert excinfo.value.exit_code == 2


def test_package_data_protection_tolerates_missing_bench(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "site" / "cora"
    (fake / "data").mkdir(parents=True)
    (fake / "data" / "cora.toml").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(shellguard, "resources", SimpleNamespace(files=lambda pkg: fake))

    dirs = shellguard.package_data_dirs()
    assert len(dirs) == 2
    assert not dirs[1].exists()

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir()
    guard = shellguard.PathGuard(ws_dir, shellguard.default_protected())
    assert guard.check(str(ws_dir / "a.txt")) is None
    finding = guard.check(str(fake / "data" / "cora.toml"))
    assert finding is not None
    assert finding.rule == "floor:protected-path"


def test_e2e_tasks_protected_when_bench_present(tmp_path: Path) -> None:
    task = Path(str(resources.files("cora") / "bench" / "e2e_tasks" / "01_todo_cli" / "task.toml"))
    assert task.is_file()
    finding = shellguard.PathGuard(tmp_path, shellguard.default_protected()).check(str(task))
    assert finding is not None and finding.rule == "floor:protected-path"


@pytest.mark.slow
def test_cli_import_loads_no_bench_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, cora.cli.main; print(sorted(m for m in sys.modules "
            "if m == 'cora.bench' or m.startswith('cora.bench.')))",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
