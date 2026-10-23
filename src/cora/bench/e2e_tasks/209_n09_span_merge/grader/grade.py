"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import importlib
import json
import os
import sys

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


def sp():
    return importlib.import_module("spans")


@check
def unsorted_overlaps():
    expect(sp().merge([(5, 8), (1, 3), (2, 4)]), [(1, 4), (5, 8)], "unsorted overlaps")


@check
def touching_merge():
    expect(sp().merge([(1, 2), (2, 3)]), [(1, 3)], "touching")


@check
def nested_and_empty():
    m = sp()
    expect(m.merge([(1, 10), (2, 3), (4, 4)]), [(1, 10)], "nested and empty")
    expect(m.merge([]), [], "empty input")


@check
def input_not_modified():
    m = sp()
    data = [(5, 8), (1, 3), (2, 4)]
    before = list(data)
    m.merge(data)
    expect(data, before, "input list")


@check
def invalid_span():
    e = raises(ValueError, sp().merge, [(1, 2), (3, 1)])
    expect(str(e), "bad span (3, 1)", "invalid span message")


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
