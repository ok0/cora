"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import json
import os
import subprocess
import sys

ROOT = os.getcwd()
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def run(*args):
    return subprocess.run(
        [sys.executable, "-B", os.path.join(ROOT, "temps.py"), *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


def converts(args, wanted):
    p = run(*args)
    expect(p.returncode, 0, f"exit code for {args!r}")
    expect(p.stdout.strip(), wanted, f"stdout for {args!r}")


@check
def c_to_f():
    converts(["100C", "F"], "212.0F")
    converts(["-40C", "F"], "-40.0F")


@check
def f_and_k():
    converts(["32F", "C"], "0.0C")
    converts(["98.6F", "C"], "37.0C")
    converts(["373.15K", "C"], "100.0C")
    converts(["26.85C", "K"], "300.0K")


@check
def case_and_same_unit():
    converts(["-40c", "f"], "-40.0F")
    converts(["5C", "C"], "5.0C")


@check
def below_absolute_zero():
    for args in (["-300C", "K"], ["-1K", "C"]):
        p = run(*args)
        expect(p.returncode, 1, f"exit code for {args!r}")
        expect(p.stderr.strip(), "error: below absolute zero", f"stderr for {args!r}")


@check
def bad_usage():
    for args in ([], ["100C"], ["100X", "F"], ["abcC", "F"]):
        p = run(*args)
        expect(p.returncode, 2, f"exit code for {args!r}")
        expect(p.stderr.startswith("usage:"), True, f"stderr for {args!r}")


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
