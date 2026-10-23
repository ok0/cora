# Text statistics library

Implement the functions in `textstats.py` (standard library only). `test_textstats.py`
is the test specification; it must keep passing (`python test_textstats.py` exits 0).

A *word* is a maximal run of ASCII letters, digits and apostrophes ('). Words are compared
case-insensitively and reported in lower case.

- `word_count(text: str) -> int` - number of words.
- `char_frequency(text: str) -> dict[str, int]` - counts of the ASCII letters a-z in `text`,
  case-insensitive; only letters that occur are keys.
- `top_words(text: str, n: int) -> list[tuple[str, int]]` - the `n` most frequent lower-cased
  words as (word, count) tuples, sorted by count (descending) then word (ascending).
  Returns [] when n <= 0.
- `average_word_length(text: str) -> float` - mean word length rounded to 2 decimals;
  0.0 when there are no words.
- `sentence_count(text: str) -> int` - each maximal run of `.`, `!` or `?` ends one sentence;
  if words appear after the last run (or there is no run at all) that trailing text counts
  as one more sentence. Text without words returns 0.
