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


def mod():
    return importlib.import_module("textstats")


def table(name, rows):
    fn = getattr(mod(), name)
    for args, wanted in rows:
        expect(fn(*args), wanted, f"{name}{args!r}")


@check
def word_count():
    table("word_count", [(("Hello, world! It's 2024.",), 4), (("",), 0), (("  --  ",), 0),
                         (("don't stop",), 2), (("a-b_c",), 3)])


@check
def char_frequency():
    table("char_frequency", [(("Hello",), {"h": 1, "e": 1, "l": 2, "o": 1}),
                             (("123 !?",), {}), (("AaZz",), {"a": 2, "z": 2})])


@check
def top_words():
    table("top_words", [(("b a b c a b", 2), [("b", 3), ("a", 2)]),
                        (("b a", 5), [("a", 1), ("b", 1)]),
                        (("The the THE cat", 1), [("the", 3)]),
                        (("x", 0), []), (("x", -1), [])])


@check
def average_word_length():
    table("average_word_length", [(("ab abcd",), 3.0), (("",), 0.0), (("a bb ccc",), 2.0),
                                  (("abc de",), 2.5), (("a ab ab",), 1.67)])


@check
def sentence_count():
    table("sentence_count", [(("One. Two!",), 2), (("Hello world",), 1),
                             (("Wait... what?!",), 2), (("Hi. Bye",), 2), (("",), 0),
                             (("?!",), 0)])


@check
def visible_spec_passes():
    proc = subprocess.run([sys.executable, "-B", "test_textstats.py"], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)
    expect(proc.returncode, 0, "python test_textstats.py exit code")


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
