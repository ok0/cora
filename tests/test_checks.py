from __future__ import annotations

from pathlib import Path

from cora.core.checks import (
    detect_check_command,
    is_python_workspace,
    snapshot_tests,
    tampered_tests,
)
from cora.core.shellguard import PathGuard


def put(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_detect_pytest_tests_dir(tmp_path: Path) -> None:
    put(tmp_path, "tests/x.txt", "")
    assert detect_check_command(tmp_path) == "python -m pytest -q"


def test_detect_pytest_test_file(tmp_path: Path) -> None:
    put(tmp_path, "test_a.py", "")
    assert detect_check_command(tmp_path) == "python -m pytest -q"


def test_detect_pytest_test_file_nested(tmp_path: Path) -> None:
    put(tmp_path, "pkg/b_test.py", "")
    assert detect_check_command(tmp_path) == "python -m pytest -q"


def test_detect_pytest_pyproject(tmp_path: Path) -> None:
    put(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\naddopts = "-q"\n')
    assert detect_check_command(tmp_path) == "python -m pytest -q"


def test_detect_pyproject_without_pytest(tmp_path: Path) -> None:
    put(tmp_path, "pyproject.toml", '[project]\nname="x"\n')
    assert detect_check_command(tmp_path) is None


def test_detect_npm(tmp_path: Path) -> None:
    put(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    assert detect_check_command(tmp_path) == "npm test"


def test_detect_npm_without_test(tmp_path: Path) -> None:
    put(tmp_path, "package.json", '{"scripts": {"build": "tsc"}}')
    assert detect_check_command(tmp_path) is None


def test_detect_npm_default_placeholder(tmp_path: Path) -> None:
    put(
        tmp_path,
        "package.json",
        '{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}',
    )
    assert detect_check_command(tmp_path) is None


def test_detect_cargo(tmp_path: Path) -> None:
    put(tmp_path, "Cargo.toml", "[package]\nname = \"x\"\n")
    assert detect_check_command(tmp_path) == "cargo test"


def test_detect_go(tmp_path: Path) -> None:
    put(tmp_path, "go.mod", "module x\n")
    assert detect_check_command(tmp_path) == "go test ./..."


def test_detect_make(tmp_path: Path) -> None:
    put(tmp_path, "Makefile", "test:\n\techo ok\n")
    assert detect_check_command(tmp_path) == "make test"


def test_detect_make_not_a_target(tmp_path: Path) -> None:
    put(tmp_path, "Makefile", "build:\n\techo\nTEST := 1\n")
    assert detect_check_command(tmp_path) is None


def test_detect_empty_and_unrelated(tmp_path: Path) -> None:
    assert detect_check_command(tmp_path) is None
    put(tmp_path, "README.md", "hi")
    put(tmp_path, "notes.txt", "hi")
    assert detect_check_command(tmp_path) is None


def test_detect_precedence(tmp_path: Path) -> None:
    put(tmp_path, "tests/test_a.py", "")
    put(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    put(tmp_path, "Cargo.toml", "[package]\n")
    put(tmp_path, "go.mod", "module x\n")
    put(tmp_path, "Makefile", "test:\n\techo ok\n")
    assert detect_check_command(tmp_path) == "python -m pytest -q"
    (tmp_path / "tests" / "test_a.py").unlink()
    (tmp_path / "tests").rmdir()
    assert detect_check_command(tmp_path) == "npm test"
    (tmp_path / "package.json").unlink()
    assert detect_check_command(tmp_path) == "cargo test"
    (tmp_path / "Cargo.toml").unlink()
    assert detect_check_command(tmp_path) == "go test ./..."
    (tmp_path / "go.mod").unlink()
    assert detect_check_command(tmp_path) == "make test"


def test_detect_ignores_outside_symlink(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    put(outside, "package.json", '{"scripts": {"test": "jest"}}')
    (ws / "package.json").symlink_to(outside / "package.json")
    assert detect_check_command(ws) is None


def test_snapshot_and_tamper(tmp_path: Path) -> None:
    put(tmp_path, "tests/test_a.py", "a\n")
    put(tmp_path, "test_b.py", "b\n")
    put(tmp_path, "x_test.go", "package x\n")
    put(tmp_path, "web/a.spec.ts", "s\n")
    put(tmp_path, "src/app.py", "app\n")
    put(tmp_path, ".cora/selftest/test_s.py", "s\n")
    snap = snapshot_tests(tmp_path)
    assert set(snap) == {"tests/test_a.py", "test_b.py", "x_test.go", "web/a.spec.ts"}
    put(tmp_path, "test_b.py", "changed\n")
    (tmp_path / "x_test.go").unlink()
    put(tmp_path, "tests/test_new.py", "n\n")
    put(tmp_path, ".cora/selftest/test_s.py", "changed\n")
    assert tampered_tests(tmp_path, snap) == ["test_b.py", "x_test.go"]


def test_is_python_workspace(tmp_path: Path) -> None:
    put(tmp_path, "a.py", "")
    assert is_python_workspace(tmp_path) is True
    other = tmp_path / "other"
    other.mkdir()
    put(other, "README.md", "")
    assert is_python_workspace(other) is False
    proj = tmp_path / "proj"
    proj.mkdir()
    put(proj, "pyproject.toml", "")
    assert is_python_workspace(proj) is True


def test_selftest_write_exemption(tmp_path: Path) -> None:
    g = PathGuard(tmp_path, ())
    assert g.check(".cora/selftest/t.py", write=True).rule == "floor:protected-write"
    g.selftest_writable = True
    assert g.check(".cora/selftest/t.py", write=True) is None
    assert g.check(".cora/policy.toml", write=True).rule == "floor:protected-write"
    assert g.check(".cora/selftest/../policy.toml", write=True) is not None
