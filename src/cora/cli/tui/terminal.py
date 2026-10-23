from __future__ import annotations

import atexit
import base64
import contextlib
import threading
from collections.abc import Callable

try:
    import termios
except ImportError:  # pragma: no cover
    termios = None  # type: ignore[assignment]

ALT_SCREEN_ON = "\x1b[?1049h"
ALT_SCREEN_OFF = "\x1b[?1049l"
MOUSE_OFF = "\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l"
PASTE_OFF = "\x1b[?2004l"
CURSOR_ON = "\x1b[?25h"
RESTORE_SEQUENCE = ALT_SCREEN_OFF + MOUSE_OFF + PASTE_OFF + CURSOR_ON
OSC52_MAX_CHARS = 100_000

def osc52(text: str) -> str | None:
    data = base64.b64encode(text.encode("utf-8")).decode("ascii")
    if len(data) > OSC52_MAX_CHARS:
        return None
    return f"\x1b]52;c;{data}\x07"

class TerminalRestorer:
    """Idempotent terminal reset: leave alt screen, mouse/paste off, cursor on, termios back."""
    def __init__(self, write: Callable[[str], None], fd: int | None) -> None:
        self._write, self._fd = write, fd
        self._saved = None
        self._done = False
        self._lock = threading.Lock()

    def install(self) -> None:
        if self._fd is not None and termios is not None:
            with contextlib.suppress(Exception):
                self._saved = termios.tcgetattr(self._fd)
        atexit.register(self.restore)

    def restore(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        with contextlib.suppress(Exception):
            self._write(RESTORE_SEQUENCE)
        if self._saved is not None and termios is not None:
            with contextlib.suppress(Exception):
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        with contextlib.suppress(Exception):
            atexit.unregister(self.restore)
