# Add task priority across the tracker

The `tracker` package (standard library only) keeps tasks in a JSON-lines file. Tasks have an
id, a title and a done flag. Add a priority to every task and expose it through the service
layer and the command line. Behaviour not mentioned here stays as it is.

## Model (`tracker.models`)
- `Task(id, title, done=False, priority="normal")` is a dataclass; `priority` is its last field.
- Allowed priorities are `low`, `normal` and `high`. Any other value raises
  `ValueError("invalid priority: X")`, where `X` is the value given.

## Storage (`tracker.storage`)
- `load(path)` returns the list of tasks. A missing file gives `[]`.
- `save(path, tasks)` writes one JSON object per line with the keys `id`, `title`, `done`
  and `priority`.
- A line without a `priority` key loads with priority `"normal"`.

## Service (`tracker.service`)
- `Tracker(path)`. `add(title, priority="normal")` stores a task and returns it. Ids are
  1 + the largest existing id, and 1 for an empty file. An invalid priority raises the
  `ValueError` above and nothing is saved.
- `complete(id)` marks the task done. An unknown id raises `KeyError`.
- `list(sort="id")` returns the tasks. `sort="id"` orders by id. `sort="priority"` orders
  `high` first, then `normal`, then `low`, and ties by id ascending. Any other `sort` value
  raises `ValueError`.

## Formatting (`tracker.formatting`)
- `render(tasks)` returns one line per task joined by `\n`; an empty list gives `""`.
- Each line is `f"{t.id:>3} [{marker}] [{'x' if t.done else ' '}] {t.title}"`, where the
  marker is `H` for high, `N` for normal and `L` for low.
- Example: id 1, title `a`, priority normal, not done gives `  1 [N] [ ] a`.

## Command line (`python -m tracker`)
- The global option `--db PATH` is required and comes before the subcommand.
- `add TITLE [--priority {low,normal,high}]` (default `normal`) stores the task and prints
  `added N`, where `N` is the new id. An invalid priority is an argparse error with exit status 2.
- `list [--sort {id,priority}]` (default `id`) prints the output of `render`.
- `done ID` marks the task done and prints `done N`. For an unknown id it prints
  `error: no task N` to stderr and exits with status 1.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.
