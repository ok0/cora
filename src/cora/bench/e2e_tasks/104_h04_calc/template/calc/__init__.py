from .evaluator import evaluate
from .parser import parse
from .tokens import tokenize


def calc(src: str, env: dict[str, float] | None = None) -> float:
    return evaluate(parse(tokenize(src)), env or {})
