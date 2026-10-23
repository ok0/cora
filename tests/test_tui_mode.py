from __future__ import annotations

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML
from cora.cli.main import app
from cora.cli.mode import choose_ui, env_flag, interactive_terminal
from cora.core.state import SessionStore

T, F = True, False


@pytest.mark.parametrize(
    ("flag", "env_value", "cfg", "stdin", "stdout", "term", "expected"),
    [
        (None, None, True, T, T, "xterm", "tui"),
        (None, None, False, T, T, "xterm", "classic"),
        (None, "1", False, T, T, "xterm", "tui"),
        (None, "0", True, T, T, "xterm", "classic"),
        (None, "off", True, T, T, "xterm", "classic"),
        (None, "false", True, T, T, "xterm", "classic"),
        (None, "bogus", False, T, T, "xterm", "classic"),
        (True, "0", False, T, T, "xterm", "tui"),
        (False, "1", True, T, T, "xterm", "classic"),
        (True, None, True, T, F, "xterm", "plain"),
        (True, None, True, F, T, "xterm", "plain"),
        (True, None, True, T, T, "dumb", "classic"),
        (True, None, True, T, T, "", "classic"),
    ],
)
def test_choose_ui_table(flag, env_value, cfg, stdin, stdout, term, expected) -> None:
    env = {"TERM": term} if term else {}
    if env_value is not None:
        env["CORA_TUI"] = env_value
    mode = choose_ui(flag, env, cfg, stdin_tty=stdin, stdout_tty=stdout)
    assert mode == expected


def test_env_flag_values() -> None:
    assert env_flag(None) is None
    assert env_flag(" TRUE ") is True
    assert env_flag("on") is True
    assert env_flag("0") is False
    assert env_flag("No") is False
    assert env_flag("bogus") is None


@pytest.mark.parametrize("variant", ["plain", "flag", "no_flag", "env", "config"])
def test_non_tty_never_enters_alt_screen(variant, scripted, ws, cfg_file, tmp_path,
                                         monkeypatch) -> None:
    args = []
    cfg = cfg_file
    if variant == "flag":
        args = ["--tui"]
    elif variant == "no_flag":
        args = ["--no-tui"]
    elif variant == "env":
        monkeypatch.setenv("CORA_TUI", "1")
    elif variant == "config":
        cfg = tmp_path / "cfg_tui.toml"
        cfg.write_text(CFG_TOML + "\n[ui]\ntui = true\n", encoding="utf-8")
    scripted.script.append("Final Answer: hi")
    result = CliRunner().invoke(
        app,
        [*args, "-w", str(ws), "-c", str(cfg), "--approval", "auto"],
        input="hello\n/exit\n",
    )
    assert result.exit_code == 0
    assert "\x1b[?1049h" not in result.output
    assert result.output.startswith("CORA - Cost-Oriented Routing Agent\n")


def test_start_repl_routes_to_tui(monkeypatch, ws, cfg_file) -> None:
    seen: dict = {}

    def fake_choose(flag, env, config_tui, *, stdin_tty, stdout_tty):
        seen["flag"] = flag
        return "tui"

    ran: list = []
    monkeypatch.setattr("cora.cli.main.choose_ui", fake_choose)
    monkeypatch.setattr("cora.cli.tui.app.run_tui", lambda *a, **k: ran.append(a) or 0)
    result = CliRunner().invoke(app, ["--tui", "-w", str(ws), "-c", str(cfg_file)])
    assert result.exit_code == 0
    assert ran
    assert seen["flag"] is True


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.stdout == "cora 0.1.0\n"
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("stdin", "stdout", "term", "expected"),
    [(T, T, "xterm", T), (T, T, "dumb", F), (T, T, " DUMB ", F), (T, T, "", F),
     (F, T, "xterm", F), (T, F, "xterm", F)],
)
def test_interactive_terminal(stdin, stdout, term, expected) -> None:
    env = {"TERM": term} if term else {}
    assert interactive_terminal(env, stdin_tty=stdin, stdout_tty=stdout) is expected


@pytest.mark.parametrize(
    ("argv", "env_value", "cfg_tui", "expected"),
    [
        ([], None, None, "tui"),
        (["--no-tui"], None, None, "classic"),
        ([], "0", None, "classic"),
        (["--tui"], "0", None, "tui"),
        ([], None, False, "classic"),
        ([], "1", False, "tui"),
        (["--no-tui"], "1", True, "classic"),
    ],
)
def test_resume_mode_priority(argv, env_value, cfg_tui, expected, ws, tmp_path,
                              monkeypatch) -> None:
    cfg = tmp_path / "cfg.toml"
    text = CFG_TOML
    if cfg_tui is not None:
        text += f"\n[ui]\ntui = {'true' if cfg_tui else 'false'}\n"
    cfg.write_text(text, encoding="utf-8")
    if env_value is None:
        monkeypatch.delenv("CORA_TUI", raising=False)
    else:
        monkeypatch.setenv("CORA_TUI", env_value)
    seen: dict = {}

    def fake_choose(flag, env, config_tui, *, stdin_tty, stdout_tty):
        seen["mode"] = choose_ui(flag, {**env, "TERM": "xterm-256color"}, config_tui,
                                 stdin_tty=True, stdout_tty=True)
        return seen["mode"]

    class FakeRepl:
        def __init__(self, io, opts) -> None:
            seen["opts"] = opts

        def run(self) -> int:
            return 0

    monkeypatch.setattr("cora.cli.main.interactive_terminal", lambda *a, **k: True)
    monkeypatch.setattr("cora.cli.main.choose_ui", fake_choose)
    monkeypatch.setattr("cora.cli.main.TerminalIO", lambda *a, **k: None)
    monkeypatch.setattr("cora.cli.main.Repl", FakeRepl)
    monkeypatch.setattr("cora.cli.tui.app.run_tui",
                        lambda opts, h, ui: seen.__setitem__("opts", opts) or 0)
    result = CliRunner().invoke(app, ["resume", "SID-1", *argv, "-w", str(ws), "-c", str(cfg)])
    assert result.exit_code == 0
    assert seen["mode"] == expected
    assert seen["opts"].resume_id == "SID-1"


def test_resume_non_tty_stays_plain(scripted, ws, cfg_file) -> None:
    scripted.script[:] = ["Final Answer: 42"]
    r = CliRunner().invoke(
        app, ["run", "q", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"]
    )
    assert r.exit_code == 0
    (sid,) = SessionStore(ws / ".cora" / "sessions").list_ids()
    r = CliRunner().invoke(app, ["resume", sid, "--tui", "-w", str(ws), "-c", str(cfg_file)])
    assert r.exit_code == 0
    assert r.stdout == "42\n"
    assert f"session: {sid}" in r.stderr
    assert "\x1b[?1049h" not in r.output
    r2 = CliRunner().invoke(app, ["resume", "nope", "-w", str(ws), "-c", str(cfg_file)])
    assert r2.exit_code == 2
    assert "session not found" in r2.stderr
