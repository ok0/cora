from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from cora.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg_file(tmp_path) -> Path:
    path = tmp_path / "cora.toml"
    path.write_text(
        """
[[models]]
id = "mock/cheap"
provider = "scripted"
tier = "cheap"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0

[[models]]
id = "mock/strong"
provider = "scripted"
tier = "strong"
input_usd_per_mtok = 5.0
output_usd_per_mtok = 10.0
""",
        encoding="utf-8",
    )
    return path


def test_one_shot(scripted, tmp_path, cfg_file):
    ws = tmp_path / "ws"
    ws.mkdir()
    scripted.script[:] = ["Final Answer: 42"]
    result = CliRunner().invoke(
        app,
        ["run", "what is 6*7", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
    )
    assert result.exit_code == 0, result.output
    assert "42" in result.output
    assert result.stdout.strip() == "42"
    assert "== CORA cost summary ==" in result.stderr


def test_chat(scripted, tmp_path, cfg_file):
    ws = tmp_path / "ws"
    ws.mkdir()
    scripted.script[:] = ["Final Answer: one", "Final Answer: two"]
    result = CliRunner().invoke(
        app,
        ["chat", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
        input="first\nsecond\n/exit\n",
    )
    assert result.exit_code == 0, result.output
    assert "one" in result.output
    assert "two" in result.output
    assert "== CORA cost summary ==" in result.output


def test_missing_key_cli(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    ws = tmp_path / "ws"
    ws.mkdir()
    result = CliRunner().invoke(
        app,
        ["run", "hi", "-c", str(REPO_ROOT / "cora.toml"), "-w", str(ws)],
    )
    assert result.exit_code == 2
    output = result.output
    if hasattr(result, "stderr"):
        output += result.stderr
    assert "OPENROUTER_API_KEY is not set" in output


def test_no_args_starts_repl(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: hi there"]
    result = CliRunner().invoke(
        app,
        ["-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
        input="hello\n/exit\n",
    )
    assert result.exit_code == 0, result.output
    assert "hi there" in result.output
    assert "/help" in result.output


def test_print_flag(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: 42"]
    result = CliRunner().invoke(
        app,
        ["-p", "what is 6*7", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "42\n"
    assert "stop_reason: final_answer" in result.stderr


def test_print_missing_config_exit2(ws, tmp_path):
    result = CliRunner().invoke(
        app,
        ["-p", "x", "-c", str(tmp_path / "nope.toml"), "-w", str(ws)],
    )
    assert result.exit_code == 2
    assert "config file not found" in result.stderr


def test_help_has_no_model_flags():
    runner = CliRunner()
    argvs = [["--help"], ["run", "--help"], ["chat", "--help"], ["resume", "--help"]]
    for argv in [*argvs, ["bench", "--help"]]:
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        for flag in ("--cheap-model", "--strong-model", "--cheap-price", "--strong-price"):
            assert flag not in result.output
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 2
    assert "No such command" in result.output
