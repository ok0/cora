from __future__ import annotations

import fcntl
import importlib.util
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

from conftest import CFG_TOML

pytestmark = [
    pytest.mark.pty,
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32" or importlib.util.find_spec("pty") is None,
                       reason="needs a POSIX pty"),
]

ENTRY = Path(__file__).with_name("tui_pty_entry.py")
CFG = CFG_TOML.replace('provider = "scripted"', 'provider = "pty_fake"')
DEADLINE_S = 20
MOUSE_ON_SEQS = (b"\x1b[?1000h", b"\x1b[?1003h", b"\x1b[?1015h", b"\x1b[?1006h")
MOUSE_OFF_SEQS = (b"\x1b[?1000l", b"\x1b[?1003l", b"\x1b[?1015l", b"\x1b[?1006l")


class Pty:
    def __init__(self, args: list[str], tmp_path: Path, env_extra: dict | None = None,
                 cols: int = 100, rows: int = 30) -> None:
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.before = termios.tcgetattr(self.slave)
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items()
               if k not in ("CORA_TUI", "NO_COLOR", "OPENROUTER_API_KEY")}
        env.update({"TERM": "xterm-256color", "HOME": str(home)})
        env.update(env_extra or {})
        self.proc = subprocess.Popen(
            [sys.executable, str(ENTRY), *args],
            stdin=self.slave, stdout=self.slave, stderr=self.slave,
            cwd=tmp_path, env=env, start_new_session=True, close_fds=True,
        )
        self.data = b""
        self.after: list | None = None

    def pump(self, timeout: float = 0.1) -> bool:
        ready, _, _ = select.select([self.master], [], [], timeout)
        if not ready:
            return False
        try:
            chunk = os.read(self.master, 65536)
        except OSError:
            return False
        self.data += chunk
        if b"\x1b[6n" in chunk:
            os.write(self.master, b"\x1b[1;1R")
        return True

    def drain(self) -> None:
        while self.pump(0.05):
            pass

    def wait_for(self, needle: bytes, timeout: float = DEADLINE_S) -> None:
        end = time.monotonic() + timeout
        while needle not in self.data:
            if self.proc.poll() is not None:
                self.drain()
                if needle in self.data:
                    return
                self.proc.kill()
                pytest.fail(f"never saw {needle!r}; output tail: {self.data[-600:]!r}")
            if time.monotonic() > end:
                self.proc.kill()
                pytest.fail(f"never saw {needle!r}; output tail: {self.data[-600:]!r}")
            self.pump()

    def send(self, data: bytes) -> None:
        os.write(self.master, data)

    def finish(self, timeout: float = DEADLINE_S) -> int:
        end = time.monotonic() + timeout
        while self.proc.poll() is None:
            if time.monotonic() > end:
                self.proc.kill()
                pytest.fail(f"process did not exit; output tail: {self.data[-600:]!r}")
            self.pump()
        self.drain()
        self.after = termios.tcgetattr(self.slave)
        os.close(self.master)
        os.close(self.slave)
        return self.proc.returncode


def _setup(tmp_path: Path, cfg_text: str = CFG) -> tuple[Path, Path]:
    ws = tmp_path / "ws"
    ws.mkdir()
    cfg = tmp_path / "cora.toml"
    cfg.write_text(cfg_text, encoding="utf-8")
    return ws, cfg


def _same_modes(before: list, after: list) -> bool:
    """termios attrs equal; macOS adds the PENDIN lflag bit on any raw->canonical round trip."""
    pendin = getattr(termios, "PENDIN", 0)
    a, b = list(before[:4]), list(after[:4])
    a[3] &= ~pendin
    b[3] &= ~pendin
    return a == b


def test_pty_tui_turn_and_exit(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    p = Pty(["-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path)
    p.wait_for(b"approval:auto")
    p.send(b"ping\r")
    p.wait_for(b"pong")
    p.send(b"/exit\r")
    rc = p.finish()
    assert rc == 0
    data = p.data
    assert data.count(b"\x1b[?1049h") == 1
    assert data.index(b"\x1b[?1049h") < data.rindex(b"\x1b[?1049l")
    tail = data.rsplit(b"\x1b[?1049l", 1)[1]
    assert b"session:" in tail
    assert b"CORA: 1 turn" in tail
    assert p.after is not None and _same_modes(p.before, p.after)


def test_pty_sigterm_restores_terminal(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    p = Pty(["-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path)
    p.wait_for(b"approval:auto")
    p.proc.send_signal(signal.SIGTERM)
    rc = p.finish()
    assert rc == 143
    after_enter = p.data[p.data.index(b"\x1b[?1049h"):]
    assert b"\x1b[?1049l" in after_enter
    assert b"\x1b[?2004l" in after_enter
    assert b"\x1b[?1000l" in after_enter
    assert b"\x1b[?1000h" in after_enter
    for seq in (b"\x1b[?1002l", b"\x1b[?1003l", b"\x1b[?1006l"):
        assert seq in after_enter[after_enter.rindex(b"\x1b[?1000h"):]
    assert p.after is not None and _same_modes(p.before, p.after)


def test_pty_mouse_on_by_default_toggle_and_restore(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    p = Pty(["-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path)
    p.wait_for(b"mouse:on")
    assert p.data.count(b"\x1b[?1000h") == 1
    assert all(s in p.data for s in MOUSE_ON_SEQS)
    n = len(p.data)
    p.send(b"/mouse off\r")
    p.wait_for(b"mouse capture: off")
    assert all(s in p.data[n:] for s in MOUSE_OFF_SEQS)
    n = len(p.data)
    p.send(b"/mouse on\r")
    p.wait_for(b"mouse capture: on")
    assert all(s in p.data[n:] for s in MOUSE_ON_SEQS)
    p.send(b"\x1b[<64;10;5M\x1b[<65;10;5M")
    p.send(b"/exit\r")
    assert p.finish() == 0
    tail = p.data[p.data.rindex(b"\x1b[?1000h"):]
    assert all(s in tail for s in (*MOUSE_OFF_SEQS, b"\x1b[?1002l"))
    assert p.after is not None and _same_modes(p.before, p.after)


@pytest.mark.parametrize("case", ["flag", "env", "config", "dumb"])
def test_pty_non_tui_modes_never_enter_alt_screen(case: str, tmp_path: Path) -> None:
    cfg_text = CFG
    extra: dict[str, str] = {}
    prefix: list[str] = []
    if case == "flag":
        prefix = ["--no-tui"]
    elif case == "env":
        extra = {"CORA_TUI": "0"}
    elif case == "config":
        cfg_text = CFG + "\n[ui]\ntui = false\n"
    elif case == "dumb":
        extra = {"TERM": "dumb"}
    ws, cfg = _setup(tmp_path, cfg_text)
    p = Pty([*prefix, "-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path,
            env_extra=extra)
    p.wait_for(b"/help")
    p.send(b"/exit\r")
    assert p.finish() == 0
    assert b"\x1b[?1049h" not in p.data


def _make_session(tmp_path: Path, ws: Path, cfg: Path) -> str:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ("CORA_TUI", "NO_COLOR", "OPENROUTER_API_KEY")}
    env.update({"TERM": "xterm-256color", "HOME": str(home)})
    r = subprocess.run([sys.executable, str(ENTRY), "-p", "first-question", "-w", str(ws),
                        "-c", str(cfg), "--approval", "auto"], stdin=subprocess.DEVNULL,
                       capture_output=True, cwd=tmp_path, env=env, timeout=DEADLINE_S)
    assert r.returncode == 0, r.stderr
    assert b"pong1" in r.stdout
    (sid,) = sorted(p.name for p in (ws / ".cora" / "sessions").iterdir())
    return sid


def test_pty_resume_opens_tui(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    sid = _make_session(tmp_path, ws, cfg)
    p = Pty(["resume", sid, "-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path)
    p.wait_for(b"Resumed session")
    p.wait_for(b"first-question")
    p.wait_for(b"pong1")
    p.send(b"again\r")
    p.wait_for(b"pong2")
    p.send(b"/exit\r")
    rc = p.finish()
    assert rc == 0
    data = p.data
    assert data.count(b"\x1b[?1049h") == 1
    assert data.index(b"\x1b[?1049h") < data.rindex(b"\x1b[?1049l")
    tail = data.rsplit(b"\x1b[?1049l", 1)[1]
    assert sid.encode() in tail
    assert b"cora resume" in tail
    assert b"CORA: 1 turn" in tail
    assert p.after is not None and _same_modes(p.before, p.after)


def test_pty_resume_no_tui_classic(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    sid = _make_session(tmp_path, ws, cfg)
    p = Pty(["resume", sid, "--no-tui", "-w", str(ws), "-c", str(cfg), "--approval", "auto"],
            tmp_path)
    p.wait_for(b"Resumed session")
    p.wait_for(b"first-question")
    p.send(b"again\r")
    p.wait_for(b"pong2")
    p.send(b"/exit\r")
    assert p.finish() == 0
    assert b"\x1b[?1049h" not in p.data
    assert sid.encode() in p.data


def test_pty_resume_dumb_term_stays_non_interactive(tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    sid = _make_session(tmp_path, ws, cfg)
    p = Pty(["resume", sid, "-w", str(ws), "-c", str(cfg), "--approval", "auto"], tmp_path,
            env_extra={"TERM": "dumb"})
    assert p.finish() == 0
    assert b"pong1" in p.data
    assert b"stop_reason: final_answer" in p.data
    assert b"\x1b[?1049h" not in p.data


@pytest.mark.parametrize("extra", [[], ["--no-tui"]])
def test_pty_resume_unknown_id(extra: list[str], tmp_path: Path) -> None:
    ws, cfg = _setup(tmp_path)
    p = Pty(["resume", "nope-id", *extra, "-w", str(ws), "-c", str(cfg)], tmp_path)
    assert p.finish() == 2
    assert b"\x1b[?1049h" not in p.data
    assert b"session not found" in p.data
    assert p.after is not None and _same_modes(p.before, p.after)
