from __future__ import annotations

from typer.testing import CliRunner

from conftest import act
from cora.cli.main import app


def test_print_mode_plain(scripted, ws, cfg_file) -> None:
    scripted.script[:] = [act("list_files", {}), "Final Answer: 42"]
    result = CliRunner().invoke(
        app, ["-p", "list", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"]
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "42"
    combined = result.stdout + result.stderr
    assert "\x1b" not in combined
    assert "CORA 0.1.0" not in combined
    assert "approval:auto" not in combined
    assert not any("─" <= ch <= "╿" for ch in combined)
    assert "● list_files (" in result.stderr
