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


def dl():
    return importlib.import_module("dotenv_lite")


@check
def basic_pairs():
    p = dl().parse
    expect(p("NAME=ada\nPORT=8080\n"), {"NAME": "ada", "PORT": "8080"}, "two pairs")
    expect(p("EMPTY=\n"), {"EMPTY": ""}, "empty value")
    expect(p("  KEY  =  spaced value  \n"), {"KEY": "spaced value"}, "whitespace stripped")
    expect(p("A=b=c\n"), {"A": "b=c"}, "split at first equals")
    expect(p(""), {}, "empty text")


@check
def comments_and_override():
    p = dl().parse
    expect(p("# top\n\n   # indented comment\nA=1\n\nB=2\n"), {"A": "1", "B": "2"}, "comments and blanks")
    expect(p("A=1\nB=2\nA=3\n"), {"A": "3", "B": "2"}, "later key overrides")
    expect(p("   \n"), {}, "whitespace-only line")


@check
def export_prefix():
    expect(dl().parse("export API_URL = https://example.test/v1\n"),
           {"API_URL": "https://example.test/v1"}, "export prefix")


@check
def quotes():
    p = dl().parse
    expect(p('NAME="Ada Lovelace"\n'), {"NAME": "Ada Lovelace"}, "double quotes")
    expect(p('GREETING="hi\\nthere"\n'), {"GREETING": "hi\nthere"}, "newline escape")
    expect(p('Q="say \\"yo\\" \\\\ ok"\n'), {"Q": 'say "yo" \\ ok'}, "quote and backslash escapes")
    expect(p("RAW='a\\nb # x'\n"), {"RAW": "a\\nb # x"}, "single quotes literal")


@check
def inline_comment():
    p = dl().parse
    expect(p("PORT=8080 # inline\n"), {"PORT": "8080"}, "inline comment removed")
    expect(p("PATH_ISH=a#b\n"), {"PATH_ISH": "a#b"}, "hash without space kept")


@check
def errors():
    p = dl().parse
    e = raises(ValueError, p, "A=1\n# c\nBROKEN\n")
    expect(str(e), "line 3: missing '='", "missing equals")
    e = raises(ValueError, p, "=x\n")
    expect(str(e), "line 1: empty key", "empty key")


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
