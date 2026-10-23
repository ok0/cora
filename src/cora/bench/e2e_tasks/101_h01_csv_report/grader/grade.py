"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def raises(exc, fn, *args):
    try:
        fn(*args)
    except exc as e:
        return e
    raise AssertionError(f"{exc.__name__} not raised")


def write_file(text):
    os.makedirs(SCRATCH, exist_ok=True)
    d = tempfile.mkdtemp(dir=SCRATCH)
    path = os.path.join(d, "data.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def cli(*args):
    return subprocess.run(
        [sys.executable, "-B", "-m", "csvreport", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


def parse_fn():
    return importlib.import_module("csvreport").parse_csv


def stats_fn():
    return importlib.import_module("csvreport").column_stats


@check
def parse_simple():
    parse = parse_fn()
    expect(parse("a,b\n1,2\n"), [["a", "b"], ["1", "2"]], "two rows")
    expect(parse("x"), [["x"]], "no trailing newline")
    expect(parse("a,,c\n"), [["a", "", "c"]], "empty field")
    expect(parse(" a , b \n"), [[" a ", " b "]], "spaces kept")
    expect(parse(""), [], "empty text")


@check
def parse_quoted():
    parse = parse_fn()
    expect(parse('"a,b",c\n'), [["a,b", "c"]], "comma in quotes")
    expect(parse('"l1\nl2",x\n'), [["l1\nl2", "x"]], "newline in quotes")
    expect(parse('"say ""hi""",z\n'), [['say "hi"', "z"]], "doubled quote")
    expect(parse('""\n'), [[""]], "empty quoted field")


@check
def parse_line_endings():
    parse = parse_fn()
    expect(parse("a,b\r\n1,2\r\n"), [["a", "b"], ["1", "2"]], "CRLF")
    expect(parse("a\n\nb\n"), [["a"], ["b"]], "empty line skipped")
    expect(parse("a\r\n\r\nb"), [["a"], ["b"]], "empty CRLF line skipped")
    expect(parse("a\n\n"), [["a"]], "trailing blank lines add no row")


@check
def parse_unterminated():
    e = raises(ValueError, parse_fn(), 'a,b\n"x\ny')
    expect(str(e), "unterminated quote at line 2", "message")


@check
def stats_basic():
    cs = stats_fn()
    rows = [["id", "v"], ["1", "1"], ["2", "3"], ["3", "5"]]
    expect(cs(rows, "v"), {"count": 3, "min": 1.0, "max": 5.0, "mean": 3.0}, "basic")
    expect(cs([["v"], ["1"], ["2"], ["2"]], "v"),
           {"count": 3, "min": 1.0, "max": 2.0, "mean": 1.67}, "rounded mean")
    expect(cs([["v"], ["-1"], ["1e1"]], "v"),
           {"count": 2, "min": -1.0, "max": 10.0, "mean": 4.5}, "float syntax")


@check
def stats_blank_and_empty():
    cs = stats_fn()
    expect(cs([["v"], [""], ["4"], [""]], "v"),
           {"count": 1, "min": 4.0, "max": 4.0, "mean": 4.0}, "blank cells ignored")
    empty = {"count": 0, "min": None, "max": None, "mean": None}
    expect(cs([["v"], [""]], "v"), empty, "only blank cells")
    expect(cs([["v"]], "v"), empty, "header only")


@check
def stats_errors():
    cs = stats_fn()
    e = raises(KeyError, cs, [["v"], ["1"]], "w")
    expect(e.args, ("w",), "unknown column argument")
    e = raises(ValueError, cs, [["v"], ["abc"]], "v")
    expect(str(e), "non-numeric value 'abc' in column 'v'", "non-numeric message")


@check
def cli_output_and_exit_codes():
    expect(callable(importlib.import_module("csvreport").main), True, "main export")
    path = write_file("id,v\n1,1\n2,3\n3,5\n")
    proc = cli(path, "v")
    expect(proc.returncode, 0, "exit code")
    expect(proc.stdout.strip(), "count=3 min=1.0 max=5.0 mean=3.0", "stdout")
    proc = cli(write_file("v\n\n"), "v")
    expect(proc.returncode, 0, "empty exit code")
    expect(proc.stdout.strip(), "count=0 min=- max=- mean=-", "empty stdout")
    missing = os.path.join(SCRATCH, "missing.csv")
    proc = cli(missing, "v")
    expect(proc.returncode, 2, "missing file exit code")
    expect(proc.stderr.strip(), f"error: file not found: {missing}", "missing file stderr")
    proc = cli(path, "zz")
    expect(proc.returncode, 2, "unknown column exit code")
    expect(proc.stderr.strip(), "error: unknown column: zz", "unknown column stderr")
    proc = cli(path)
    expect(proc.returncode, 2, "usage exit code")
    expect(proc.stderr.strip(), "usage: python -m csvreport FILE COLUMN", "usage stderr")


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
