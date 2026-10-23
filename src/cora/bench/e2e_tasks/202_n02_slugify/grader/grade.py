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


@check
def basic():
    tk = importlib.import_module("textkit")
    expect(tk.slugify("Hello, World!"), "hello-world", "hello world")
    expect(tk.slugify("Version 2.0 Released"), "version-2-0-released", "version")


@check
def accents():
    tk = importlib.import_module("textkit")
    expect(tk.slugify("Crème Brûlée à la carte"), "creme-brulee-a-la-carte", "accents")


@check
def separators_collapse():
    tk = importlib.import_module("textkit")
    expect(tk.slugify("  a -- b__c  "), "a-b-c", "separators")
    expect(tk.slugify("!!!"), "", "no letters or digits")


@check
def max_length():
    tk = importlib.import_module("textkit")
    text = "the quick brown fox"
    expect(tk.slugify(text, 12), "the-quick", "max 12")
    expect(tk.slugify(text, 9), "the-quick", "max 9")
    expect(tk.slugify(text, 10), "the-quick", "max 10")
    expect(tk.slugify("abcdefghij", 4), "abcd", "max 4 inside word")
    expect(tk.slugify(text, 100), "the-quick-brown-fox", "max 100")


@check
def max_length_invalid():
    tk = importlib.import_module("textkit")
    e = raises(ValueError, tk.slugify, "abc", 0)
    expect(str(e), "max_length must be >= 1", "message")


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
