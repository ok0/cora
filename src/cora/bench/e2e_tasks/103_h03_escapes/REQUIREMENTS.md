# Escaping helpers

Implement the `escapes` package in this directory. Some functions are stubs that raise
`NotImplementedError`; implement them. Keep the module names and function names.
Do not change the `ENTITIES` table in `escapes/catalog.py`.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.

## Shell quoting: `escapes.shell.quote(arg: str) -> str`

- An empty string gives `''`.
- A string made only of the characters `A-Z a-z 0-9 _ @ % + = : , . / -` is returned unchanged.
- Any other string is wrapped in single quotes, and each `'` inside it is written as `'"'"'`.
  Examples: `it's` gives `'it'"'"'s'`, `a b` gives `'a b'`, `$HOME` gives `'$HOME'`.

## JSON strings: `escapes.jsonstr` (must not import `json`)

- `encode(s: str) -> str` returns a JSON string literal, with surrounding `"`.
  `"` is written `\"`, `\` is written `\\`, and `\b \f \n \r \t` are written with those short
  forms. Any other character below 0x20 is written `\u00xx` with lowercase hex digits.
  All other characters are written as they are (`/` is not escaped; non-ASCII is not escaped).
  Example: the string `a"b\c` + newline gives the literal `"a\"b\\c\n"`.
- `decode(lit: str) -> str` is the inverse for JSON string literals. It accepts `\"`, `\\`, `\/`,
  `\b`, `\f`, `\n`, `\r`, `\t`, and `\uXXXX` (hex digits in either case). A surrogate pair such as
  `\ud83d\ude00` decodes to one character (U+1F600).
- `decode` raises `ValueError` when:
  - `lit` does not start and end with `"` (a text of length 1 included);
  - a backslash is followed by any other character (for example `\q`), or ends the text;
  - a `\u` is not followed by exactly four hex digits;
  - a high surrogate `\uD800`-`\uDBFF` is not immediately followed by a `\uDC00`-`\uDFFF` escape, or
    a low surrogate `\uDC00`-`\uDFFF` appears without a preceding high surrogate.
- `decode(encode(s)) == s` for every string `s`.

## Windows paths: `escapes.winpath.to_posix(path: str) -> str`

- Every `\` is treated as `/`.
- A drive letter `X:` at the start followed by `/` or the end of the text becomes `/x` (letter
  lowercased). Examples: `C:\Users\a b\x.txt` gives `/c/Users/a b/x.txt`; `C:\` gives `/c`.
- A leading `//` (UNC prefix, from `\\server\share`) is kept as `//`. Example:
  `\\server\share\f.txt` gives `//server/share/f.txt`.
- Repeated `/` are collapsed to one, except in the leading UNC prefix.
- One trailing `/` is removed. Example: `C:\tmp\` gives `/c/tmp`.
- Other text is kept as it is. Example: `dir\file.txt` gives `dir/file.txt`.

## HTML entities: `escapes.catalog.unescape_html(s: str) -> str`

- `ENTITIES` maps HTML entity names to code points. It must stay unchanged.
- `&name;` is replaced by the character of `ENTITIES[name]` when `name` is in `ENTITIES`
  (case-sensitive). Example: `&eacute;` gives `é`, `&lt;p&gt;` gives `<p>`.
- Numeric references are also decoded: `&#NNN;` (decimal) and `&#xHH;` or `&#XHH;` (hex, digits in
  either case). Examples: `&#65;` gives `A`, `&#x4a;` gives `J`, `&#x1F600;` gives `😀`.
- Any other text is kept unchanged. Example: `&bogus;` stays `&bogus;`.
- Each reference is decoded once: `&#38;amp;` gives `&amp;`.
