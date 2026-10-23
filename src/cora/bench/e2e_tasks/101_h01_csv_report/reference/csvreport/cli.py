import sys

from .parser import parse_csv
from .stats import column_stats

USAGE = "usage: python -m csvreport FILE COLUMN"


def _show(value) -> str:
    return "-" if value is None else str(value)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    path, column = argv
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    try:
        stats = column_stats(parse_csv(text), column)
    except KeyError:
        print(f"error: unknown column: {column}", file=sys.stderr)
        return 2
    print(
        f"count={stats['count']} min={_show(stats['min'])} "
        f"max={_show(stats['max'])} mean={_show(stats['mean'])}"
    )
    return 0
