from __future__ import annotations

from .errors import CalcError
from .parser import Binary, Call, Num, Unary, Var


def evaluate(node: object, env: dict[str, float]) -> float:
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Var):
        if node.name not in env:
            raise CalcError(f"unknown variable '{node.name}'", -1)
        return float(env[node.name])
    if isinstance(node, Unary):
        value = evaluate(node.operand, env)
        return -value if node.op == "-" else value
    if isinstance(node, Binary):
        left = evaluate(node.left, env)
        right = evaluate(node.right, env)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            if right == 0:
                raise CalcError("division by zero", -1)
            return left / right
        if node.op == "%":
            if right == 0:
                raise CalcError("division by zero", -1)
            return left % right
        return left ** right
    if isinstance(node, Call):
        args = [evaluate(arg, env) for arg in node.args]
        if node.name in ("min", "max"):
            if not args:
                raise CalcError(f"wrong number of arguments for '{node.name}'", -1)
            return min(args) if node.name == "min" else max(args)
        if node.name == "abs":
            if len(args) != 1:
                raise CalcError("wrong number of arguments for 'abs'", -1)
            return abs(args[0])
        raise CalcError(f"unknown function '{node.name}'", -1)
    raise TypeError(f"unknown node {node!r}")
