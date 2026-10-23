from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from importlib import resources
from pathlib import Path

import pytest

from conftest import CFG_TOML
from cora.cli.main import BENCH_MISSING
from cora.core.config import find_config, load_config
from cora.core.sale import load_tier_table

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "cora" / "data"
SKIP_MARKERS = ("offline", "network", "cache")


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    return uv


def _skip_or_fail(result: subprocess.CompletedProcess[str], what: str) -> None:
    err = result.stderr.lower()
    if any(marker in err for marker in SKIP_MARKERS):
        pytest.skip(f"{what} needs an offline/cache-warm uv: {result.stderr.strip()[-300:]}")
    assert result.returncode == 0, f"{what} failed:\n{result.stderr}"


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    uv = _uv()
    out = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        [uv, "build", "--wheel", "--offline", "--out-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    _skip_or_fail(result, "uv build --wheel")
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


@pytest.mark.install
def test_wheel_ships_data_without_bench(wheel: Path) -> None:
    names = zipfile.ZipFile(wheel).namelist()
    for p in DATA.iterdir():
        if p.is_file():
            assert f"cora/data/{p.name}" in names, p.name
    assert [n for n in names if n.startswith("cora/bench/")] == []
    assert any(n.startswith("cora/core/") for n in names)
    assert any(n.startswith("cora/cli/") for n in names)
    assert "cora/data/cora.toml" in names
    entry_points = zipfile.ZipFile(wheel).read(
        next(n for n in names if n.endswith("entry_points.txt"))
    ).decode("utf-8")
    assert "cora = cora.cli.main:app" in entry_points


@pytest.mark.install
def test_uv_tool_install_runs_outside_repo(wheel: Path, tmp_path: Path) -> None:
    uv = _uv()
    tmp = tmp_path
    home = tmp / "home"
    home.mkdir()
    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    cache = subprocess.run(
        [uv, "cache", "dir"], capture_output=True, text=True, timeout=60, check=True,
    ).stdout.strip()
    env = os.environ.copy()
    env.update(
        UV_TOOL_DIR=str(tmp / "tools"),
        UV_TOOL_BIN_DIR=str(tmp / "bin"),
        UV_CACHE_DIR=cache,
        HOME=str(home),
    )
    env.pop("OPENROUTER_API_KEY", None)
    install = subprocess.run(
        [uv, "tool", "install", "--offline", str(wheel)],
        env=env, cwd=tmp, capture_output=True, text=True, timeout=300,
    )
    _skip_or_fail(install, "uv tool install")
    cora = tmp / "bin" / "cora"

    version = subprocess.run(
        [str(cora), "--version"], env=env, cwd=elsewhere,
        capture_output=True, text=True, timeout=60,
    )
    assert version.returncode == 0, version.stderr
    assert version.stdout == "cora 0.1.0\n"

    helped = subprocess.run(
        [str(cora), "--help"], env=env, cwd=elsewhere,
        capture_output=True, text=True, timeout=60,
    )
    assert helped.returncode == 0, helped.stderr

    prompt = subprocess.run(
        [str(cora), "-p", "hi"], env=env, cwd=elsewhere,
        capture_output=True, text=True, timeout=60,
    )
    assert prompt.returncode == 2
    assert "OPENROUTER_API_KEY is not set" in prompt.stderr

    def _cora(*args: str, input: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(cora), *args], env=env, cwd=elsewhere, input=input,
            capture_output=True, text=True, timeout=60,
        )

    headless = _cora("run", "x", "--headless", "--json")
    assert headless.returncode == 2
    assert json.loads(headless.stdout)["exit_code"] == 2
    assert "Traceback" not in headless.stderr

    mcp = _cora("mcp", "serve", input="")
    assert mcp.returncode == 0
    assert "Traceback" not in mcp.stderr

    for args in (
        ("bench",),
        ("bench", "plan"),
        ("bench", "compare", "report.json"),
        ("decider", "eval"),
        ("sale", "eval"),
    ):
        res = _cora(*args)
        assert res.returncode == 2, args
        assert res.stderr.count(BENCH_MISSING) == 1, args
        assert "Traceback" not in res.stdout + res.stderr, args

    for args in (
        ("bench", "--help"),
        ("bench", "plan", "--help"),
        ("bench", "compare", "--help"),
        ("decider", "--help"),
        ("sale", "--help"),
    ):
        res = _cora(*args)
        assert res.returncode == 0, args


def test_config_discovery_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    cwd = tmp_path.resolve() / "proj"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(cwd)

    bundled = Path(str(resources.files("cora") / "data" / "cora.toml"))
    assert find_config(None) == bundled
    load_config(find_config(None))

    user_cfg = home / ".config" / "cora" / "cora.toml"
    user_cfg.parent.mkdir(parents=True)
    user_cfg.write_text(CFG_TOML, encoding="utf-8")
    assert find_config(None) == user_cfg

    project_cfg = cwd / "cora.toml"
    project_cfg.write_text(CFG_TOML, encoding="utf-8")
    assert find_config(None) == project_cfg


def test_bundled_data_loads_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    load_config(find_config(None))
    load_tier_table(None)


def test_src_has_no_repo_relative_paths() -> None:
    for path in (ROOT / "src" / "cora").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "__file__" not in text, path
        assert "parents[" not in text, path
