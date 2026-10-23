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


def conv(src):
    return importlib.import_module("md2html").convert(src)


@check
def headings():
    expect(conv("# Title\n\n### Sub"), "<h1>Title</h1>\n<h3>Sub</h3>\n", "headings")
    expect(conv("#nope"), "<p>#nope</p>\n", "not a heading")


@check
def paragraphs():
    expect(conv("one\ntwo\n\nthree"), "<p>one two</p>\n<p>three</p>\n", "paragraphs")
    expect(conv(""), "", "empty input")
    expect(conv("\n  \n"), "", "blank lines only")


@check
def lists():
    expect(conv("- a\n- b\n\ntext"), "<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n<p>text</p>\n",
           "list")


@check
def code_block():
    expect(conv("```\nx < 1 *y*\n```"), "<pre><code>x &lt; 1 *y*</code></pre>\n", "code block")


@check
def inline_emphasis():
    expect(conv("**b** and *e* and `c`"),
           "<p><strong>b</strong> and <em>e</em> and <code>c</code></p>\n", "emphasis")


@check
def links():
    expect(conv("[home](http://x.y/)"), '<p><a href="http://x.y/">home</a></p>\n', "link")
    expect(conv("a [b](c) d"), '<p>a <a href="c">b</a> d</p>\n', "link inside text")


@check
def escaping():
    expect(conv("a < b & c > d"), "<p>a &lt; b &amp; c &gt; d</p>\n", "escaping")


@check
def cli():
    os.makedirs(SCRATCH, exist_ok=True)
    d = tempfile.mkdtemp(dir=SCRATCH)
    path = os.path.join(d, "in.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Hi\n\ntext")
    proc = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "md2html.py"), path],
                          cwd=ROOT, capture_output=True, text=True, timeout=10)
    expect((proc.returncode, proc.stdout), (0, "<h1>Hi</h1>\n<p>text</p>\n"), "cli output")


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
