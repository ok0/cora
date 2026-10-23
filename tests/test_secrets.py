from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from cora.cli.main import app

DUMMY = "sk-or-v1-DUMMY-not-a-real-key-000"
REPO_ROOT = Path(__file__).resolve().parents[1]

CONFIG_TOML = """
[providers.openrouter]
api_key_env = "OPENROUTER_API_KEY"

[[models]]
id = "test/cheap"
provider = "openrouter"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0
supports_tools = true

[[models]]
id = "test/strong"
provider = "openrouter"
tier = "strong"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[bench]
models = ["test/cheap"]
"""


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY)
    monkeypatch.setattr("cora.core.providers.openrouter.RETRY_DELAYS_S", (0, 0))
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CONFIG_TOML, encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    return cfg, ws, tmp_path / "out"


def _install(monkeypatch, fake) -> None:
    monkeypatch.setattr(httpx.AsyncClient, "send", fake)


def _assert_no_leak(result, out: Path) -> None:
    assert DUMMY not in result.stdout
    assert DUMMY not in result.stderr
    for path in out.rglob("*"):
        if path.is_file():
            assert DUMMY not in path.read_text(encoding="utf-8", errors="replace"), path


def _invoke(cfg: Path, ws: Path, out: Path):
    return CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(ws),
            "--tasks",
            "explore_find_port",
            "--protocols",
            "react,native",
            "--out",
            str(out),
        ],
    )


def test_success_path_no_leak(monkeypatch, setup):
    cfg, ws, out = setup

    async def fake(self, request, **kw):
        assert request.headers["authorization"] == f"Bearer {DUMMY}"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Final Answer: 8731"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00001},
                "model": "test/cheap",
            },
            request=request,
        )

    _install(monkeypatch, fake)
    result = _invoke(cfg, ws, out)
    assert result.exit_code == 0, result.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["provider_cost_calls"] == 2
    _assert_no_leak(result, out)


def test_http_error_path_no_leak(monkeypatch, setup):
    cfg, ws, out = setup

    async def fake(self, request, **kw):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"limit_remaining": None}}, request=request)
        return httpx.Response(401, text=f"bad {request.headers['authorization']}", request=request)

    _install(monkeypatch, fake)
    result = _invoke(cfg, ws, out)
    assert result.exit_code == 3, result.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in report["results"]] == ["error", "not_run"]
    _assert_no_leak(result, out)


def test_transport_error_path_no_leak(monkeypatch, setup):
    cfg, ws, out = setup

    async def fake(self, request, **kw):
        raise httpx.ConnectError(f"boom {DUMMY}")

    _install(monkeypatch, fake)
    result = _invoke(cfg, ws, out)
    assert result.exit_code == 0, result.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert {r["status"] for r in report["results"]} == {"error"}
    _assert_no_leak(result, out)


def test_repo_has_no_real_key_pattern():
    pattern = re.compile(r"sk-or-v1-[0-9a-f]{32,}")
    roots = [REPO_ROOT / "src", REPO_ROOT / "tests", REPO_ROOT / ".docs"]
    files = [REPO_ROOT / "README.md", REPO_ROOT / "cora.toml", REPO_ROOT / "pyproject.toml"]
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    hits = [
        str(p)
        for p in files
        if p.exists() and pattern.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert hits == []
