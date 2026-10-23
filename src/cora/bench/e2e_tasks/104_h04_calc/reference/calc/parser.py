from __future__ import annotations

from dataclasses import dataclass

from .errors import CalcError
from .tokens import Token


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: object


@dataclass(frozen=True)
class Binary:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> Token | None:
        if self.index < len(self.tokens):
            return self.tokens[self.index]
        return None

    def advance(self) -> Token | None:
        tok = self.peek()
        self.index += 1
        return tok

    def end_pos(self) -> int:
        if not self.tokens:
            return 0
        last = self.tokens[-1]
        return last.pos + len(last.text)

    def is_op(self, tok: Token | None, ops: tuple[str, ...]) -> bool:
        return tok is not None and tok.kind == "op" and tok.text in ops

    def expr(self) -> object:
        node = self.term()
        while self.is_op(self.peek(), ("+", "-")):
            op = self.advance().text
            node = Binary(op, node, self.term())
        return node

    def term(self) -> object:
        node = self.unary()
        while self.is_op(self.peek(), ("*", "/", "%")):
            op = self.advance().text
            node = Binary(op, node, self.unary())
        return node

    def unary(self) -> object:
        if self.is_op(self.peek(), ("+", "-")):
            op = self.advance().text
            return Unary(op, self.unary())
        return self.power()

    def power(self) -> object:
        base = self.atom()
        if self.is_op(self.peek(), ("^",)):
            self.advance()
            return Binary("^", base, self.unary())
        return base

    def atom(self) -> object:
        tok = self.advance()
        if tok is None:
            raise CalcError("unexpected end of input", self.end_pos())
        if tok.kind == "num":
            return Num(float(tok.text))
        if tok.kind == "name":
            nxt = self.peek()
            if nxt is not None and nxt.kind == "lparen":
                self.advance()
                args = [self.expr()]
                while self.peek() is not None and self.peek().kind == "comma":
                    self.advance()
                    args.append(self.expr())
                self.close()
                return Call(tok.text, tuple(args))
            return Var(tok.text)
        if tok.kind == "lparen":
            node = self.expr()
            self.close()
            return node
        raise CalcError(f"unexpected token '{tok.text}' at {tok.pos}", tok.pos)

    def close(self) -> None:
        tok = self.peek()
        if tok is None:
            raise CalcError("unexpected end of input", self.end_pos())
        if tok.kind != "rparen":
            raise CalcError(f"expected ')' at {tok.pos}", tok.pos)
        self.index += 1


def parse(tokens: list[Token]) -> object:
    parser = _Parser(tokens)
    node = parser.expr()
    tok = parser.peek()
    if tok is not None:
        raise CalcError(f"unexpected token '{tok.text}' at {tok.pos}", tok.pos)
    return node
