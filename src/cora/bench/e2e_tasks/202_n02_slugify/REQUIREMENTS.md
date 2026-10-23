# Slug helper

`textkit.py` has two finished helpers, `word_count` and `title_case`. Add `slugify` to it.
Leave the other two functions unchanged.

`slugify(text: str, max_length: int | None = None) -> str` turns text into a URL slug.

- Normalize with NFKD, drop every non-ASCII character, then lowercase.
- Every run of characters other than `a-z` and `0-9` becomes one `-`.
- Strip leading and trailing `-`.
- Input with no letters or digits gives `""`.
- Examples: `"Hello, World!"` gives `"hello-world"`; `"Version 2.0 Released"` gives
  `"version-2-0-released"`; `"Crème Brûlée à la carte"` gives `"creme-brulee-a-la-carte"`;
  `"  a -- b__c  "` gives `"a-b-c"`; `"!!!"` gives `""`.

With `max_length`:

- If the slug is longer than `max_length`, cut it to `max_length` characters.
- If the cut falls inside a word (the next character of the full slug is not `-`) and the cut
  part contains a `-`, cut back to the last `-`.
- Then strip trailing `-`.
- Examples for `"the quick brown fox"`: `max_length=12` gives `"the-quick"`; `max_length=9` gives
  `"the-quick"`; `max_length=10` gives `"the-quick"`; `max_length=100` gives
  `"the-quick-brown-fox"`. For `"abcdefghij"` with `max_length=4`, the result is `"abcd"`.
- `max_length < 1` raises `ValueError("max_length must be >= 1")`.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.
