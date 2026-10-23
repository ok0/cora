# .env file parser

Finish `dotenv_lite.py` in this directory. `parse` is a stub that raises `NotImplementedError`;
implement it. `dump` is already done and must stay as it is.

`python -m pytest -q` runs a few tests; they do not cover everything.

## Format

- One `KEY=VALUE` pair per line. Split each line at the first `=`; strip whitespace around the key
  and around the value.
- Blank lines are skipped. A line whose stripped form starts with `#` is a comment and is skipped.
- An optional `export ` prefix (the word `export` followed by a space) before the key is removed.
- A later pair with the same key overrides the earlier value.

## Values

- Double quotes: the value is unquoted, and these escapes are applied inside: `\n` becomes a newline,
  `\"` becomes `"`, and `\\` becomes a single backslash.
- Single quotes: the value is unquoted and kept literal. No escapes are applied.
- Unquoted: an inline comment starts at a space followed by `#` (` #`). That space and everything
  after it are removed. A `#` without a space before it is part of the value.

## Examples

```
NAME="Ada Lovelace"        -> {"NAME": "Ada Lovelace"}
GREETING="hi\nthere"       -> {"GREETING": "hi" + newline + "there"}
RAW='a\nb # x'             -> {"RAW": "a\\nb # x"}      (backslash-n kept literally)
PORT=8080 # inline         -> {"PORT": "8080"}
PATH_ISH=a#b               -> {"PATH_ISH": "a#b"}
export API_URL = https://example.test/v1  -> {"API_URL": "https://example.test/v1"}
EMPTY=                     -> {"EMPTY": ""}
```

## Errors

Line numbers are 1-based and count every line of the input, including blank and comment lines.

- A non-blank, non-comment line with no `=` raises `ValueError(f"line {n}: missing '='")`.
- A line whose key is empty (for example `=x`) raises `ValueError(f"line {n}: empty key")`.

Example: for the three-line text `A=1`, `# c`, `BROKEN`, the error is `line 3: missing '='`.

## Function

- `parse(text: str) -> dict[str, str]`: parses the whole text and returns the pairs as a dict.
- `dump(d: dict[str, str]) -> str` (already implemented): writes `KEY=VALUE` lines, one per pair.
