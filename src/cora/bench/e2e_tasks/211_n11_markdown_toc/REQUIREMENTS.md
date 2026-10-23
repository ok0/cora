# Markdown table of contents

Write a module `mdtoc.py` that builds a table of contents from Markdown text. It provides two functions: `slug` and `toc`.

## slug(heading) -> str

Turn the text of a heading into an anchor name.

- Convert the text to lower case.
- Keep only characters for which `isalnum()` is true, plus the space, `-` and `_` characters. Drop all other characters.
- Replace each space with `-`. Do not collapse repeated dashes.

Examples:

- `slug("Hello, World!")` returns `hello-world`
- `slug("C++ & Python 3")` returns `c--python-3`

## toc(markdown, min_level=1, max_level=3) -> str

Return one line for each heading whose level is between `min_level` and `max_level` (inclusive), in document order.

Which lines are headings:

- Only ATX headings count: one to six `#` characters, then a space, at the very start of the line.
- `#NoSpace` is not a heading. A line with seven or more `#` characters is not a heading.
- Lines inside fenced code blocks are never headings. A fence opens with three backticks or three tildes at the start of a line. An info string after the opening fence is allowed.
- A fence closes at the next line that starts with the same three characters. A `~~~` block does not close on a line that starts with three backticks, and the other way round.

Heading text:

- The text is the rest of the line after the `#` characters and the space, with surrounding whitespace removed.
- Closing hashes are removed. For example, `### Deep ###` has the text `Deep`.
- Backtick characters are removed. For example, a heading whose text is `Getting` followed by the word `started` wrapped in backticks has the text `Getting started`.

Output:

- Each heading becomes one line `- [TEXT](#ANCHOR)` followed by a newline.
- Indent each line by two spaces for every level below `min_level`. A heading at level `min_level` has no indent.
- ANCHOR is `slug(TEXT)`. If an earlier heading in the document already produced the same anchor, append `-1`, `-2`, and so on, in document order.
- Count every heading in the document for this, including headings outside the level range.
- If no heading is in range, return an empty string.

Errors:

- If `min_level` or `max_level` is outside 1 to 6, or `min_level` is greater than `max_level`, raise `ValueError`.

Example:

    toc("# Guide\n## Install\n### Linux\n")

returns

    - [Guide](#guide)
      - [Install](#install)
        - [Linux](#linux)

and with `min_level=2, max_level=2` it returns

    - [Install](#install)

`python -m pytest -q` runs a few tests; they do not cover everything.
