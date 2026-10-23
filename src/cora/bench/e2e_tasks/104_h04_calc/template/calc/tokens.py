from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


def tokenize(src: str) -> list[Token]:
    raise NotImplementedError
