from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import CalcError


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


_TOKEN_RE = re.compile(
    r"(?P<num>[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op>[-+*/%^])"
    r"|(?P<lparen>\()"
    r"|(?P<rparen>\))"
    r"|(?P<comma>,)"
)


def tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(src):
        if src[pos].isspace():
            pos += 1
            continue
        match = _TOKEN_RE.match(src, pos)
        if match is None:
            raise CalcError(f"unexpected character '{src[pos]}' at {pos}", pos)
        kind = match.lastgroup
        tokens.append(Token(kind, match.group(kind), pos))
        pos = match.end()
    return tokens
