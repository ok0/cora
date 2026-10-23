# Gradebook averages and report

Finish the `gradebook` package in this directory. Some functions are stubs that raise
`NotImplementedError`; implement them. Keep `gradebook/models.py` and `gradebook/__init__.py` as they are.

`python -m pytest -q` runs a few tests; they do not cover everything.

## Weighted average (`gradebook/stats.py`)

`weighted_average(student) -> float` uses the `WEIGHTS` dict from `gradebook/models.py`
(homework 0.3, midterm 0.3, final 0.4). Each category contributes its weight times the
student's score in it. A category with no score counts as 0. The result is `round(x, 2)`.
For example, `{"homework": 90, "midterm": 80, "final": 85}` gives `85.0`, and
`{"homework": 100, "midterm": 100}` gives `60.0`.

## Letter grades

`letter(avg) -> str` returns:

- `A` for avg >= 90
- `B` for avg >= 80
- `C` for avg >= 70
- `D` for avg >= 60
- `F` otherwise

If avg < 0 or avg > 100, raise `ValueError(f"score out of range: {avg}")`.
For example, `letter(-1)` raises `ValueError` with the message `score out of range: -1`, and
`letter(100.01)` raises it with the message `score out of range: 100.01`.

## Ranking

`rank(students) -> list[tuple[str, float, str]]` returns one `(name, avg, letter)` tuple per
student, where avg is that student's weighted average. The list is sorted by average, highest
first. Students with equal averages are sorted by name, ascending.

## Command-line report (`gradebook/cli.py`)

`python -m gradebook.cli FILE` reads a CSV file. The first line is a header that must contain
the columns `name`, `homework`, `midterm` and `final`. Each following line is one student.
An empty cell means that category is missing for the student. Any other cell is read as a number.

On success the command prints one line per student, in the order of `rank`, formatted as
`f"{name:<12}{avg:>7.2f} {letter}"`, and exits with status 0.

- If FILE cannot be read, print `error: cannot read FILE` (with the path given) to stderr and exit with status 1.
- If a column is missing from the header, print `error: missing column <col>` to stderr and exit with status 2.
  `<col>` is the first missing column in the order `name`, `homework`, `midterm`, `final`.
