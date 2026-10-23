"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
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


def stats():
    return importlib.import_module("gradebook.stats")


def student(name, scores):
    return importlib.import_module("gradebook.models").Student(name, scores)


def scratch():
    os.makedirs(os.path.join(ROOT, ".cora_grader"), exist_ok=True)
    return tempfile.mkdtemp(dir=os.path.join(ROOT, ".cora_grader"))


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-B", "-m", "gradebook.cli", *args],
        capture_output=True, text=True, timeout=10, cwd=ROOT,
    )


@check
def weighted_average_basic():
    avg = stats().weighted_average(student("ann", {"homework": 90, "midterm": 80, "final": 85}))
    assert abs(avg - 85.0) < 1e-9, f"expected 85.0, got {avg!r}"


@check
def missing_category_zero():
    avg = stats().weighted_average(student("ann", {"homework": 100, "midterm": 100}))
    assert abs(avg - 60.0) < 1e-9, f"expected 60.0, got {avg!r}"


@check
def letter_boundaries():
    lt = stats().letter
    cases = [(100, "A"), (90, "A"), (89.99, "B"), (80, "B"), (70, "C"), (60, "D"), (59.99, "F"), (0, "F")]
    for value, wanted in cases:
        expect(lt(value), wanted, f"letter({value})")


@check
def letter_out_of_range():
    for value in (-1, 100.01):
        e = raises(ValueError, stats().letter, value)
        expect(str(e), f"score out of range: {value}", f"message for {value}")


@check
def rank_order_ties():
    rows = stats().rank([
        student("cy", {"homework": 100, "midterm": 100}),
        student("bob", {"homework": 90, "midterm": 80, "final": 85}),
        student("ann", {"homework": 90, "midterm": 80, "final": 85}),
    ])
    expect(rows, [("ann", 85.0, "B"), ("bob", 85.0, "B"), ("cy", 60.0, "D")], "rank")


@check
def cli_output():
    path = os.path.join(scratch(), "grades.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("name,homework,midterm,final\n")
        f.write("bob,90,80,85\nann,90,80,85\ncy,100,100,\n")
    r = run_cli(path)
    expect(r.returncode, 0, "exit code")
    expected = [
        f"{name:<12}{avg:>7.2f} {grade}"
        for name, avg, grade in [("ann", 85.0, "B"), ("bob", 85.0, "B"), ("cy", 60.0, "D")]
    ]
    expect(r.stdout.splitlines(), expected, "stdout lines")


@check
def cli_errors():
    d = scratch()
    r = run_cli(os.path.join(d, "absent.csv"))
    expect(r.returncode, 1, "missing file exit code")
    assert "error: cannot read" in r.stderr, r.stderr
    path = os.path.join(d, "nofinal.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("name,homework,midterm\nann,90,80\n")
    r = run_cli(path)
    expect(r.returncode, 2, "missing column exit code")
    assert "error: missing column final" in r.stderr, r.stderr


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
