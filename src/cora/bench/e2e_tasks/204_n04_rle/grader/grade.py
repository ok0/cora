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


def rle():
    return importlib.import_module("rle")


@check
def encode_basic():
    enc = rle().encode
    expect(enc("aaabcc"), "3a1b2c", "aaabcc")
    expect(enc(""), "", "empty")
    expect(enc("  x"), "2 1x", "two spaces")
    expect(enc("ééx"), "2é1x", "non-ascii")


@check
def encode_long_runs():
    expect(rle().encode("a" * 12 + "b"), "12a1b", "long run")


@check
def encode_rejects_digits():
    e = raises(ValueError, rle().encode, "ab1")
    expect(str(e), "digits not allowed", "digit message")


@check
def decode_roundtrip():
    m = rle()
    for s in ["", "aaabcc", "  x", "ééx", "a" * 12 + "b", "xyz"]:
        expect(m.decode(m.encode(s)), s, f"roundtrip {s!r}")


@check
def decode_malformed():
    d = rle().decode
    for bad in ["a", "3", "0a", "3a2", "03a"]:
        e = raises(ValueError, d, bad)
        expect(str(e), "bad input", f"message for {bad!r}")


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
