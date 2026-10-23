from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cora.cli.main import app
from cora.core.agent import Agent
from cora.core.config import load_config
from cora.core.router import HeuristicRouter
from cora.core.tools import ApprovalPolicy

ROOT = Path(__file__).resolve().parents[1]
TOMLS = [ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml"]


@pytest.mark.parametrize("path", TOMLS, ids=["repo", "packaged"])
def test_lenient_parse_on_in_shipped_tomls(path: Path) -> None:
    assert load_config(path).agent.lenient_parse is True
    assert TOMLS[0].read_bytes() == TOMLS[1].read_bytes()


def test_agent_does_not_import_sale() -> None:
    code = "import sys, cora.core.agent; print('cora.core.sale' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    ).stdout.strip()
    assert out == "False"


def test_delegate_absent_by_default(tmp_path: Path) -> None:
    agent = Agent(load_config(ROOT / "cora.toml"), tmp_path, ApprovalPolicy("auto"))
    assert "delegate" not in agent.registry_for().names()


def test_sale_help_says_experimental() -> None:
    result = CliRunner().invoke(app, ["sale", "--help"])
    assert result.exit_code == 0
    assert "Experimental" in result.output


def test_default_run_without_openrouter_key_exit_2(
    monkeypatch: pytest.MonkeyPatch, no_network, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = CliRunner().invoke(
        app, ["run", "q", "-w", str(tmp_path), "-c", str(ROOT / "cora.toml")]
    )
    assert result.exit_code == 2
    assert "OPENROUTER_API_KEY" in result.stderr


def test_default_cheap_is_openrouter_flash_lite() -> None:
    router = HeuristicRouter(load_config(ROOT / "cora.toml"))
    cheap = router.resolve("cheap")
    assert (cheap.id, cheap.provider) == ("google/gemini-2.5-flash-lite", "openrouter")
    assert cheap.free_tier is False
