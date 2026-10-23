from calc import calc
from calc.tokens import Token, tokenize


def test_tokenize_basic():
    assert tokenize("2 + x1") == [
        Token("num", "2", 0),
        Token("op", "+", 2),
        Token("name", "x1", 4),
    ]


def test_precedence():
    assert calc("1 + 2 * 3") == 7
    assert calc("2^3^2") == 512
    assert calc("-2^2") == -4


def test_variables_and_functions():
    assert calc("x * max(1, y)", {"x": 2, "y": 5}) == 10
    assert calc("abs(-3)") == 3
