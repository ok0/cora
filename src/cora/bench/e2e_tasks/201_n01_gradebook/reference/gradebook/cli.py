"""Print a ranked gradebook report from a CSV file."""

import csv
import sys

from .models import Student
from .stats import rank

COLUMNS = ["name", "homework", "midterm", "final"]
CATEGORIES = ["homework", "midterm", "final"]


def main(argv: list[str] | None = None) -> int:
    """Run the report for the CSV file in argv and return the exit status."""
    args = sys.argv[1:] if argv is None else argv
    path = args[0]
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            rows = list(reader)
    except OSError:
        print(f"error: cannot read {path}", file=sys.stderr)
        return 1
    for column in COLUMNS:
        if column not in header:
            print(f"error: missing column {column}", file=sys.stderr)
            return 2
    index = {column: header.index(column) for column in COLUMNS}
    students = []
    for row in rows:
        if not row:
            continue
        scores = {}
        for category in CATEGORIES:
            cell = row[index[category]]
            if cell != "":
                scores[category] = float(cell)
        students.append(Student(row[index["name"]], scores))
    for name, avg, grade in rank(students):
        print(f"{name:<12}{avg:>7.2f} {grade}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
