from __future__ import annotations

import re
from dataclasses import dataclass

TRIP_THRESHOLD = 3

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\w.~-]*/)+[\w.~-]*")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-f]{7,40}\b")
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def normalize_error(text: str) -> str:
    text = text[-4000:]
    text = _ANSI.sub("", text)
    text = _PATH.sub("<path>", text)
    text = _HEX.sub("<hex>", text)
    text = _NUM.sub("0", text)
    text = _WS.sub(" ", text)
    return text.strip()


@dataclass
class Tripwire:
    threshold: int = TRIP_THRESHOLD
    last: tuple[str, str, str] | None = None
    streak: int = 0
    tripped: tuple[str, str, str] | None = None
    head: str = ""

    def observe(self, kind: str, name: str, output: str) -> bool:
        if self.tripped:
            return True
        key = (kind, name, normalize_error(output))
        if key == self.last:
            self.streak += 1
        else:
            self.last, self.streak = key, 1
        if self.streak >= self.threshold:
            self.tripped = key
            self.head = output[:300]
            return True
        return False

    def reset(self) -> None:
        self.last = None
        self.streak = 0
        self.tripped = None
        self.head = ""
