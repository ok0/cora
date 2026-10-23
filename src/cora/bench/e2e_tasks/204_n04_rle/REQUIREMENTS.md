# Run-length encoding

Implement `rle.py` with two functions: `encode(s: str) -> str` and `decode(s: str) -> str`.

- `encode` replaces each run of equal characters with the run length followed by the character.
- `encode("aaabcc")` returns `"3a1b2c"`.
- `encode("")` returns `""`.
- Run lengths may be greater than 9: `encode("a" * 12 + "b")` returns `"12a1b"`.
- Spaces are ordinary characters: `encode("  x")` returns `"2 1x"`.
- Non-ASCII letters are ordinary characters: `encode("ééx")` returns `"2é1x"`.
- If the input contains any decimal digit (`0` to `9`), `encode` raises `ValueError("digits not allowed")`.
- `decode` is the inverse of `encode`: `decode(encode(s)) == s` for every valid input `s`.
- `decode("3a1b2c")` returns `"aaabcc"`.
- `decode("")` returns `""`.
- A count is one or more digits followed by exactly one character.
- A count has no leading zero and is at least 1.
- Malformed input makes `decode` raise `ValueError("bad input")`. Examples of malformed input:
  - a character without a count, such as `"a"`
  - a count without a following character, such as `"3"` or `"3a2"`
  - a count of 0, such as `"0a"`
  - a leading zero, such as `"03a"`

`python -m pytest -q` runs a few tests; they do not cover everything.
