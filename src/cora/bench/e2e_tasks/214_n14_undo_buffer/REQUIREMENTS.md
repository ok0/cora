# Text buffer with undo

Finish the `editbuf` package in this directory. Some functions are stubs that raise
`NotImplementedError`; implement them. Keep `editbuf/__init__.py` and the `Edit` class in
`editbuf/history.py` as they are.

Positions are character indexes. `Buffer(text="", max_undo=100)` starts with that text and no undo
history. `max_undo < 1` raises `ValueError`. `text` is the current text.

- `insert(pos, s)`: raises `IndexError` unless `0 <= pos <= len(text)`, even when `s` is empty.
  An empty `s` changes nothing and is not recorded.
- `delete(pos, n)`: raises `IndexError` unless `pos >= 0`, `n >= 0` and `pos + n <= len(text)`.
  `n == 0` changes nothing and is not recorded.
- `undo()` reverts the latest undo group and returns True. It returns False if there is none.
- `redo()` re-applies the most recently undone group and returns True. It returns False if there is
  none.
- Any recorded edit clears the redo history. A no-op is not recorded and does not clear it.
- Only the latest `max_undo` groups are kept.

Grouping:

- A one-character insert joins the previous group when the previous recorded edit is an insert
  that ends exactly at `pos`, and the last character of that group is not a space or a newline.
- Every multi-character insert and every delete forms its own group.
- `undo()` and `redo()` end the current group, so the next insert never joins a group.

Examples: typing `hello` one character at a time makes one group, so one `undo()` gives an empty
text. Typing `hello world` one character at a time gives the groups `hello ` and `world`, so
`undo()` gives `hello ` and a second `undo()` gives an empty text.
