# Expression calculator

Finish the `calc` package so that `calc(src, env=None)` evaluates an arithmetic expression
and returns a float. `env` maps variable names to numbers. The package already has the
public function `calc` in `calc/__init__.py`, the error class `CalcError` in `calc/errors.py`
and the `Token` dataclass in the `calc.tokens` module. Keep those public names and their
behaviour. Do not use `eval`, `exec` or `compile` anywhere in the package.

## Tokens (`calc.tokens`)
- `Token(kind, text, pos)` is a frozen dataclass; `pos` is the 0-based index of the token's first character.
- `tokenize(src)` returns the list of tokens. Whitespace is ignored; whitespace-only input gives `[]`.
- Kinds: `num`, `name`, `op`, `lparen`, `rparen`, `comma`.
- Numbers: digits with an optional fraction (`3`, `2.5`) or a fraction without integer part (`.5`).
- Names: a letter or underscore followed by letters, digits or underscores.
- Operators: `+ - * / % ^`.
- Any other character raises `CalcError("unexpected character 'C' at N", N)` where `C` is the character and `N` its index.

## Parsing and evaluation
- Precedence from lowest to highest: binary `+ -` (left-associative); binary `* / %` (left-associative); unary `+ -`; `^` (right-associative). The right operand of `^` may carry a unary sign.
- Parentheses group sub-expressions.
- Functions: `min(a, b, ...)` and `max(...)` take one or more arguments; `abs(a)` takes exactly one.
- Examples: `1 + 2 * 3` is 7; `10 - 4 - 3` is 3; `2^3^2` is 512; `-2^2` is -4; `(-2)^2` is 4; `2^-1` is 0.5; `min(4, 2, 9)` is 2; `abs(-7.5)` is 7.5.
- `calc` returns floats.

## Errors
Every error is a `CalcError`; `str(e)` equals the message and `e.pos` holds the position given below.
- Input ends where an operand or a `)` is still needed (including empty input): `unexpected end of input`.
- A `)` is required but another token is found: `expected ')' at N`, where `N` is the position of that token.
- A token that cannot appear at that point, including a token left over after a complete expression: `unexpected token 'X' at N`, where `N` is the position of that token.
- A variable that is not in `env`: `unknown variable 'x'`.
- A function name that is not known: `unknown function 'f'`.
- A function called with the wrong number of arguments: `wrong number of arguments for 'abs'`.
- Division or modulo by zero: `division by zero`.

Examples: `1 +` -> `unexpected end of input`; `(1 2)` -> `expected ')' at 3`; `1 2` -> `unexpected token '2' at 2`; `2 * x$` -> `unexpected character '$' at 5`.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.
