# Todo CLI

Build a command-line todo list in `todo.py` (Python 3 standard library only).
Run it as `python todo.py <command> [args]` from any directory. Items are stored in
`todo.json` in the current working directory as a JSON list of objects
`{"id": <int>, "text": <str>, "done": <bool>}` in id order. A missing file means an empty list.

Commands (stdout lines end with a newline; exit code 0 unless stated):

- `add TEXT` - add an item. Its id is 1 + the largest existing id (1 for an empty list).
  Print `added <id>: <text>`.
- `list` - print one line per item: `<id> [ ] <text>` (open) or `<id> [x] <text>` (done).
  Print `no items` when the list is empty.
- `done ID` - mark the item done and print `done <id>`.
- `remove ID` - delete the item and print `removed <id>`.
- For `done`/`remove` with an id that does not exist (or is not an integer), print
  `error: no item <ID>` to stderr and exit with code 1.
- Any other usage (no command, unknown command, missing argument) prints
  `usage: todo.py add TEXT | list | done ID | remove ID` to stderr and exits with code 2.
