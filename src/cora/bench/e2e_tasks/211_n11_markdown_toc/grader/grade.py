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


def md():
    return importlib.import_module("mdtoc")


@check
def basic_nesting():
    m = md()
    expect(m.toc("# A\n## B\n"), "- [A](#a)\n  - [B](#b)\n", "two levels")
    expect(m.toc("# Top\n### Deep\n## Mid\n"),
           "- [Top](#top)\n    - [Deep](#deep)\n  - [Mid](#mid)\n", "three levels")
    expect(m.toc("# A\n#### Four\n"), "- [A](#a)\n", "default max level 3")
    expect(m.toc(""), "", "empty document")
    expect(m.toc("plain text\n"), "", "no headings")


@check
def closing_hashes_and_code_spans():
    m = md()
    expect(m.toc("### Deep ###\n"), "    - [Deep](#deep)\n", "closing hashes")
    expect(m.toc("## Getting `started`\n"), "  - [Getting started](#getting-started)\n", "code span")


@check
def fenced_blocks_ignored():
    m = md()
    doc = "\n".join([
        "# Real",
        "```python",
        "# not a heading",
        "## nor this",
        "```",
        "~~~",
        "# also not",
        "```",
        "still code",
        "~~~",
        "## Second",
        "",
    ])
    expect(m.toc(doc), "- [Real](#real)\n  - [Second](#second)\n", "both fence kinds")


@check
def duplicate_slugs():
    m = md()
    expect(m.toc("# Getting started\n## Getting started\n", 1, 2),
           "- [Getting started](#getting-started)\n  - [Getting started](#getting-started-1)\n",
           "duplicate anchors")


@check
def level_range_and_counting():
    m = md()
    doc = "# A\n#### A\n## A\n"
    expect(m.toc(doc, 1, 3), "- [A](#a)\n  - [A](#a-2)\n", "out-of-range heading counts")
    expect(m.toc(doc, 2, 2), "- [A](#a-2)\n", "min equals max")


@check
def slug_and_invalid_range():
    m = md()
    expect(m.slug("C++ & Python 3"), "c--python-3", "symbols")
    expect(m.slug("Hello, World!"), "hello-world", "punctuation")
    raises(ValueError, m.toc, "# A\n", 3, 2)
    raises(ValueError, m.toc, "# A\n", 0, 2)
    raises(ValueError, m.toc, "# A\n", 1, 7)
    expect(m.toc("#NoSpace\n# Real\n"), "- [Real](#real)\n", "no space after hashes")
    expect(m.toc("####### Seven\n", 1, 6), "", "seven hashes")


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
