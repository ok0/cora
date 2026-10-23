# Merge time spans

Implement `spans.py` with two functions: `covered(spans, x) -> bool` and `merge(spans) -> list`.

- A span is a tuple `(start, end)` meaning the half-open interval `[start, end)`.
- `covered(spans, x)` returns `True` when `start <= x < end` for at least one span, otherwise `False`.
- `merge(spans)` takes a list of `(start, end)` tuples and returns a new list of tuples, sorted by start.
- Overlapping spans are merged: `merge([(5, 8), (1, 3), (2, 4)])` returns `[(1, 4), (5, 8)]`.
- Touching spans are merged: `merge([(1, 2), (2, 3)])` returns `[(1, 3)]`.
- A span nested inside another is absorbed: `merge([(1, 10), (2, 3), (4, 4)])` returns `[(1, 10)]`.
- Empty spans (`start == end`) are dropped: `merge([(4, 4)])` returns `[]`.
- `merge([])` returns `[]`.
- The input list and its tuples are not modified.
- If any span has `start > end`, `merge` raises `ValueError` with the message `bad span (s, e)`, where `s` and `e` are that span's start and end.
- For example, `merge([(3, 1)])` raises `ValueError` with the message `bad span (3, 1)`.
