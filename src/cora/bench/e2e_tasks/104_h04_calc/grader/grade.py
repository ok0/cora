"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import ast
import dataclasses
import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def _calc(src, env=None):
    return importlib.import_module("calc").calc(src, env)


def _error(src, env=None):
    errors = importlib.import_module("calc.errors")
    try:
        _calc(src, env)
    except errors.CalcError as e:
        return e
    raise AssertionError(f"no CalcError for {src!r}")


@check
def tokenize_basic():
    tok = importlib.import_module("calc.tokens")
    got = [(t.kind, t.text, t.pos) for t in tok.tokenize("3 + x_1*(2.5)")]
    expect(got, [("num", "3", 0), ("op", "+", 2), ("name", "x_1", 4), ("op", "*", 7),
                 ("lparen", "(", 8), ("num", "2.5", 9), ("rparen", ")", 12)], "tokens")
    got = [(t.kind, t.text, t.pos) for t in tok.tokenize(".5, min")]
    expect(got, [("num", ".5", 0), ("comma", ",", 2), ("name", "min", 4)], "tokens 2")
    expect(tok.tokenize("   "), [], "whitespace only")


@check
def precedence():
    expect(_calc("1 + 2 * 3"), 7, "1 + 2 * 3")
    expect(_calc("(1 + 2) * 3"), 9, "(1 + 2) * 3")
    expect(_calc("10 - 4 - 3"), 3, "10 - 4 - 3")
    expect(_calc("8 / 4 / 2"), 1, "8 / 4 / 2")
    expect(_calc("7 % 4 * 2"), 6, "7 % 4 * 2")


@check
def power_and_unary():
    expect(_calc("2^3^2"), 512, "2^3^2")
    expect(_calc("-2^2"), -4, "-2^2")
    expect(_calc("(-2)^2"), 4, "(-2)^2")
    expect(_calc("2^-1"), 0.5, "2^-1")
    expect(_calc("--3"), 3, "--3")
    expect(_calc("2*-3"), -6, "2*-3")
    expect(_calc("+4"), 4, "+4")


@check
def variables_and_functions():
    expect(_calc("x*2 + y", {"x": 3, "y": 1}), 7, "x*2 + y")
    expect(_calc("min(4, 2, 9)"), 2, "min(4, 2, 9)")
    expect(_calc("max(1, x)", {"x": 5}), 5, "max(1, x)")
    expect(_calc("abs(-7.5)"), 7.5, "abs(-7.5)")
    expect(_calc("min(3)"), 3, "min(3)")
    expect(_calc("max(x, y) ^ 2", {"x": 2, "y": 3}), 9, "max(x, y) ^ 2")


@check
def errors_lexer():
    e = _error("2 * x$")
    expect(e.message, "unexpected character '$' at 5", "message")
    expect(e.pos, 5, "pos")
    expect(str(e), "unexpected character '$' at 5", "str")
    expect(str(_error("1 + $")), "unexpected character '$' at 4", "second case")


@check
def errors_parser():
    expect(str(_error("1 +")), "unexpected end of input", "dangling operator")
    expect(str(_error("")), "unexpected end of input", "empty input")
    expect(str(_error("(1 + 2")), "unexpected end of input", "unclosed paren at end")
    e = _error("(1 2)")
    expect(str(e), "expected ')' at 3", "missing paren")
    expect(e.pos, 3, "missing paren pos")
    e = _error("1 2")
    expect(str(e), "unexpected token '2' at 2", "leftover token")
    expect(e.pos, 2, "leftover token pos")
    e = _error("1 + * 2")
    expect(str(e), "unexpected token '*' at 4", "bad operand")
    expect(e.pos, 4, "bad operand pos")


@check
def errors_runtime():
    expect(str(_error("x + 1")), "unknown variable 'x'", "unknown variable")
    expect(str(_error("x + 1", {})), "unknown variable 'x'", "unknown variable with env")
    expect(str(_error("foo(1)")), "unknown function 'foo'", "unknown function")
    expect(str(_error("abs(1, 2)")), "wrong number of arguments for 'abs'", "arity")
    expect(str(_error("1 / (2 - 2)")), "division by zero", "division")
    expect(str(_error("7 % (3 - 3)")), "division by zero", "modulo")


@check
def no_eval():
    for name in sorted(os.listdir(os.path.join(ROOT, "calc"))):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ROOT, "calc", name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("eval", "exec", "compile")):
                raise AssertionError(f"calc/{name} calls {node.func.id}")


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
