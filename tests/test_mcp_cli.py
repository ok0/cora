from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, act, run_repl
from cora.cli.main import app
from mcp_util import FAKE, alive, starts, toml_server

ROOT = Path(__file__).resolve().parents[1]


def _stderr_env_server(name: str, log: Path) -> str:
    args = [str(FAKE), "--mode", "stderr_env", "--log", str(log), "--env-var", "MY_TOKEN"]
    return (
        f"\n[mcp.servers.{name}]\ncommand = {json.dumps(sys.executable)}\n"
        f"args = {json.dumps(args)}\n"
        'env = { MY_TOKEN = "tok-12345" }\n'
    )


def test_repl_tools_toggle_and_sizes(scripted, ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + toml_server("fake", log), encoding="utf-8")
    scripted.script.extend(["Final Answer: a", "Final Answer: b"])
    lines = [
        "/tools mcp:fake off",
        "first",
        "/tools mcp:fake on",
        "second",
        "/tools",
        "/tools mcp:fake off",
        "/tools",
        "/exit",
    ]
    out = run_repl(ws, cfg, lines)
    assert "mcp__fake__echo" not in scripted.calls[0].messages[0].content
    assert "mcp__fake__echo" in scripted.calls[1].messages[0].content
    assert "tool group mcp:fake: off" in out
    totals = [int(v) for v in re.findall(r"enabled total: react (\d+) chars", out)]
    assert len(totals) == 2 and totals[0] > totals[1]
    rows = [ln for ln in out.splitlines() if ln.lstrip().startswith("mcp:fake")]
    assert rows and " off " in rows[-1]
    assert len(starts(log)) == 1
    for pid in starts(log):
        assert not alive(pid)


def test_repl_mcp_status_never_starts(scripted, ws, tmp_path, no_network):
    log_on = tmp_path / "on.jsonl"
    log_off = tmp_path / "off.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(
        CFG_TOML
        + toml_server("on1", log_on)
        + toml_server("off1", log_off, extra="enabled = false\n")
        + "\n[mcp.servers.bad]\nargs = []\n",
        encoding="utf-8",
    )
    out = run_repl(ws, cfg, ["/mcp", "/exit"])

    def row(name: str) -> str:
        return next(ln for ln in out.splitlines() if ln.strip().startswith(name))

    assert "not started" in row("on1")
    assert "disabled" in row("off1")
    assert "failed" in row("bad")
    assert "'command' is required" in out
    assert "warning:" in out and "bad" in out
    assert starts(log_on) == []
    assert starts(log_off) == []


def test_repl_mcp_none(scripted, ws, cfg_file):
    out = run_repl(ws, cfg_file, ["/mcp", "/mcp x", "/exit"])
    assert "No MCP servers configured" in out
    assert "usage: /mcp" in out


def test_repl_mcp_hides_env_values(scripted, ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + _stderr_env_server("srv", log), encoding="utf-8")
    scripted.script.extend([act("mcp__srv__echo", {"text": "x"}), "Final Answer: ok"])
    out = run_repl(ws, cfg, ["go", "/mcp", "/exit"])
    assert "tok-12345" not in out
    assert "[REDACTED]" in out


def test_repl_exception_path_cleans_up(scripted, ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + toml_server("fake", log), encoding="utf-8")
    scripted.script.extend([act("mcp__fake__echo", {"text": "x"}), "Final Answer: ok"])
    with pytest.raises(RuntimeError):
        run_repl(ws, cfg, ["go", RuntimeError("boom")])
    for pid in starts(log):
        assert not alive(pid)


def test_cora_run_cleans_up(scripted, ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + toml_server("fake", log), encoding="utf-8")
    scripted.script.extend([act("mcp__fake__echo", {"text": "x"}), "Final Answer: ok"])
    res = CliRunner().invoke(
        app, ["run", "go", "-c", str(cfg), "-w", str(ws), "--approval", "auto"]
    )
    assert res.exit_code == 0
    assert starts(log)
    for pid in starts(log):
        assert not alive(pid)


def test_cora_run_exception_cleans_up(scripted, ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + toml_server("fake", log), encoding="utf-8")

    def boom(req):
        raise RuntimeError("boom")

    scripted.script.extend([act("mcp__fake__echo", {"text": "x"}), boom])
    CliRunner().invoke(app, ["run", "go", "-c", str(cfg), "-w", str(ws), "--approval", "auto"])
    for pid in starts(log):
        assert not alive(pid)


def test_mcp_list(ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(
        CFG_TOML
        + toml_server("good", log)
        + '\n[mcp.servers.broken]\ncommand = "cora-no-such-command-xyz"\n',
        encoding="utf-8",
    )
    res = CliRunner().invoke(app, ["mcp", "list", "-c", str(cfg), "-w", str(ws)])
    assert res.exit_code == 0, res.output
    assert "good  ok  12 tools" in res.output
    assert "mcp__good__echo" in res.output
    assert "broken  failed" in res.output
    assert "cannot start" in res.output
    for pid in starts(log):
        assert not alive(pid)


def test_mcp_list_none(cfg_file, ws):
    res = CliRunner().invoke(app, ["mcp", "list", "-c", str(cfg_file), "-w", str(ws)])
    assert res.exit_code == 0
    assert "No MCP servers configured" in res.output
    bogus = CliRunner().invoke(app, ["mcp", "bogus", "-c", str(cfg_file), "-w", str(ws)])
    assert bogus.exit_code == 2


def test_mcp_list_hides_env(ws, tmp_path, no_network):
    log = tmp_path / "log.jsonl"
    cfg = tmp_path / "cora.toml"
    cfg.write_text(CFG_TOML + _stderr_env_server("srv", log), encoding="utf-8")
    res = CliRunner().invoke(app, ["mcp", "list", "-c", str(cfg), "-w", str(ws)])
    assert res.exit_code == 0
    assert "tok-12345" not in res.output


def test_usage_documents_mcp():
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for needle in [
        "[mcp.servers.<name>]",
        "`command`",
        "`args`",
        "`env`",
        "`enabled`",
        "`timeout_s`",
        "/mcp",
        "cora mcp list",
        "mcp:<server>",
        "OPENROUTER_API_KEY",
        "readOnlyHint",
        "알려진 제한",
    ]:
        assert needle in text, needle
