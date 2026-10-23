# Job planner and schedule simulation

Finish the `jobplan` package. Stubs raise `NotImplementedError`; implement them.
Keep `jobplan/model.py` and `jobplan/__init__.py` as they are.
`python -m pytest -q` runs a few tests; they do not cover everything.

`load_jobs(text)` (`jobplan/loader.py`) parses a JSON array of objects:
- `name`: required non-empty string. `duration`: required int >= 1 (bools and strings rejected).
- `deps`: optional list of names, default `[]`, stored as a tuple.
- `priority`: optional int, may be negative, default `0` (bools rejected).

Errors raise `JobError` with exactly these messages (N = 1-based position):
`invalid JSON`, `expected a JSON array`, `job N: missing name`,
`job N: duration must be a positive integer`, `job N: deps must be a list of names`,
`job N: priority must be an integer`, `duplicate job 'x'` (second job with the same name).

`validate(jobs)` (`jobplan/graph.py`) raises `JobError`:
- Unknown dependency: `job 'a' depends on unknown 'b'` (a = the job holding the dep).
  Checked first, in input order.
- Cycle: `cycle: a -> b -> c -> a`. Start at the smallest job name on a cycle. From the
  current job, follow the smallest dependency that still leads back to the start without
  repeating a job. A self-dependency gives `cycle: x -> x`.

`order(jobs)` returns names in dispatch order: repeatedly take the ready job (all deps already
placed) with the highest priority; ties go to the smaller name. `order` and `simulate` call
`validate` first.

`simulate(jobs, workers)` (`jobplan/simulate.py`) uses identical workers numbered from 0.
Time starts at 0. At each time t, workers whose job ended at or before t are freed, and a job is
ready when every dep ended at or before t. Free workers, lowest number first, take ready jobs in
priority-descending, name-ascending order. Then time jumps to the next job end.
`workers < 1` raises `ValueError("workers must be >= 1")`.
`Schedule` holds `starts`, `ends`, `worker` (dicts by name) and `makespan` (largest end, 0 if no jobs).

`render(schedule)` (`jobplan/report.py`) writes one line per job, sorted by start then worker,
formatted as `f"{start:>4} {end:>4}  w{worker}  {name}"`, then `makespan N`. Lines are joined
with `\n` and the text ends with `\n`.

## Example

Jobs: `fetch` (2), `build` (3, deps `fetch`), `lint` (1, priority 5), `test` (4, deps `build`,
priority 1), `docs` (2, deps `fetch`).

- `order`: `lint, fetch, build, test, docs`.
- 2 workers: lint w0 0-1, fetch w1 0-2, build w0 2-5, docs w1 2-4, test w0 5-9, makespan 9.
