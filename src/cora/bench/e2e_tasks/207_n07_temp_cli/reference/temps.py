"""Temperature converter command line tool."""

import sys

UNITS = ("C", "F", "K")
USAGE = "usage: temps.py <value><unit> <target>  (units: C, F, K)"
ABSOLUTE_ZERO_C = -273.15


def to_celsius(value: float, unit: str) -> float:
    if unit == "C":
        return value
    if unit == "F":
        return (value - 32) * 5 / 9
    return value - 273.15


def from_celsius(celsius: float, unit: str) -> float:
    if unit == "C":
        return celsius
    if unit == "F":
        return celsius * 9 / 5 + 32
    return celsius + 273.15


def main(argv: list[str]) -> int:
    """Convert one temperature and print it. Return the process exit code."""
    if len(argv) != 2:
        print(USAGE, file=sys.stderr)
        return 2
    source, target = argv[0], argv[1].upper()
    unit = source[-1:].upper()
    if unit not in UNITS or target not in UNITS:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        value = float(source[:-1])
    except ValueError:
        print(USAGE, file=sys.stderr)
        return 2
    celsius = to_celsius(value, unit)
    if celsius < ABSOLUTE_ZERO_C:
        print("error: below absolute zero", file=sys.stderr)
        return 1
    result = from_celsius(celsius, target)
    print(f"{result:.1f}{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
