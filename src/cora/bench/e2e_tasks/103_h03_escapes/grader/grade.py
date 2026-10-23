"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import ast
import html.entities
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


def mod(name):
    return importlib.import_module(name)


@check
def shell_quote():
    q = mod("escapes.shell").quote
    expect(q(""), "''", "empty")
    expect(q("abc-1.txt"), "abc-1.txt", "safe chars unchanged")
    expect(q("x=1,y:2@%+/_"), "x=1,y:2@%+/_", "safe punctuation unchanged")
    expect(q("it's"), "'it'\"'\"'s'", "single quote")
    expect(q("a b"), "'a b'", "space")
    expect(q("$HOME"), "'$HOME'", "dollar")
    expect(q("a\\b"), "'a\\b'", "backslash")


@check
def json_encode_basic():
    enc = mod("escapes.jsonstr").encode
    expect(enc("abc"), '"abc"', "plain")
    expect(enc('a"b\\c'), '"a\\"b\\\\c"', "quote and backslash")
    expect(enc("\b\f\n\r\t"), '"\\b\\f\\n\\r\\t"', "short escapes")
    expect(enc("a/b"), '"a/b"', "slash not escaped")
    expect(enc("\u00e9\u4e2d"), '"\u00e9\u4e2d"', "non-ASCII literal")


@check
def json_encode_control():
    enc = mod("escapes.jsonstr").encode
    expect(enc("\x00\x1f"), '"\\u0000\\u001f"', "nul and unit separator")
    expect(enc("\x0b"), '"\\u000b"', "vertical tab lowercase hex")
    expect(enc("\x7f"), '"\x7f"', "DEL is literal")


@check
def json_decode_roundtrip():
    m = mod("escapes.jsonstr")
    samples = [
        "",
        "plain",
        'q"uote\\back',
        "tab\there\nnl\r",
        "\x00\x01\x1f",
        "\u00e9\u4e2d",
        "\U0001F600",
        "a/b",
    ]
    for s in samples:
        expect(m.decode(m.encode(s)), s, f"roundtrip of {s!r}")
    expect(m.decode('"\\/"'), "/", "escaped slash")
    expect(m.decode('"\\ud83d\\ude00"'), "\U0001F600", "surrogate pair")
    expect(m.decode('"\\u00E9"'), "\u00e9", "uppercase hex")


@check
def json_decode_invalid():
    dec = mod("escapes.jsonstr").decode
    raises(ValueError, dec, "abc")
    raises(ValueError, dec, '"abc')
    raises(ValueError, dec, '"')
    raises(ValueError, dec, "")
    raises(ValueError, dec, '"\\q"')
    raises(ValueError, dec, '"\\')
    raises(ValueError, dec, '"\\u12"')
    raises(ValueError, dec, '"\\u12G4"')
    raises(ValueError, dec, '"\\u"')
    raises(ValueError, dec, '"\\ud83d"')
    raises(ValueError, dec, '"\\ude00"')
    raises(ValueError, dec, '"\\ud83dx"')


@check
def json_no_stdlib():
    path = os.path.join(ROOT, "escapes", "jsonstr.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] != "json", "jsonstr.py imports json"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "json", "jsonstr.py imports json"


@check
def winpath():
    tp = mod("escapes.winpath").to_posix
    expect(tp("C:\\Users\\a b\\x.txt"), "/c/Users/a b/x.txt", "drive path")
    expect(tp("\\\\server\\share\\f.txt"), "//server/share/f.txt", "UNC path")
    expect(tp("C:/Users//a\\b/"), "/c/Users/a/b", "mixed separators and trailing")
    expect(tp("C:\\tmp\\"), "/c/tmp", "trailing separator")
    expect(tp("C:\\"), "/c", "bare drive")
    expect(tp("d:\\x"), "/d/x", "lowercase drive")
    expect(tp("a\\\\b//c"), "a/b/c", "repeated separators")
    expect(tp("dir\\file.txt"), "dir/file.txt", "relative path")


@check
def html_numeric_entities():
    unescape = mod("escapes.catalog").unescape_html
    expect(unescape("&#65;&#x42;&#X43;"), "ABC", "decimal and hex")
    expect(unescape("&#233;"), "\u00e9", "decimal non-ASCII")
    expect(unescape("&#x1F600;"), "\U0001F600", "hex astral")
    expect(unescape("&#x4a;&#X4A;&#74;"), "JJJ", "hex case and decimal")
    expect(unescape("&#38;amp;"), "&amp;", "single pass")
    expect(unescape("&lt;p&gt;"), "<p>", "named still works")
    expect(unescape("&eacute;"), "\u00e9", "named entity")


@check
def html_catalog_intact():
    cat = mod("escapes.catalog")
    expect(cat.ENTITIES == html.entities.name2codepoint, True, "ENTITIES unchanged")
    expect(cat.unescape_html("&bogus;"), "&bogus;", "unknown name stays")


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
