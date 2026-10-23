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


def buf_mod():
    return importlib.import_module("editbuf.buffer")


@check
def insert_delete_basic():
    b = buf_mod().Buffer("hello")
    expect(b.text, "hello", "initial")
    b.insert(5, " world")
    expect(b.text, "hello world", "append")
    b.insert(0, ">")
    expect(b.text, ">hello world", "prepend")
    b.delete(0, 1)
    b.delete(5, 6)
    expect(b.text, "hello", "deletes")
    b.insert(2, "")
    b.delete(1, 0)
    expect(b.text, "hello", "no-ops")
    expect(buf_mod().Buffer().text, "", "default text")


@check
def bounds_errors():
    m = buf_mod()
    b = m.Buffer("ab")
    raises(IndexError, b.insert, 3, "x")
    raises(IndexError, b.insert, -1, "x")
    raises(IndexError, b.insert, 3, "")
    raises(IndexError, b.delete, 1, 2)
    raises(IndexError, b.delete, -1, 1)
    raises(IndexError, b.delete, 0, -1)
    expect(b.text, "ab", "unchanged after errors")
    expect(b.undo(), False, "no edit recorded by failures")
    b.delete(2, 0)
    b.insert(2, "c")
    expect(b.text, "abc", "valid edges")


@check
def undo_redo():
    m = buf_mod()
    b = m.Buffer()
    b.insert(0, "abc")
    b.insert(3, "def")
    expect(b.undo(), True, "undo 1")
    expect(b.text, "abc", "after undo 1")
    expect(b.undo(), True, "undo 2")
    expect(b.text, "", "after undo 2")
    expect(b.undo(), False, "nothing left")
    expect(b.redo(), True, "redo 1")
    expect(b.text, "abc", "after redo 1")
    expect(b.redo(), True, "redo 2")
    expect(b.text, "abcdef", "after redo 2")
    expect(b.redo(), False, "nothing to redo")
    b.delete(0, 3)
    expect(b.text, "def", "delete")
    expect(b.undo(), True, "undo delete")
    expect(b.text, "abcdef", "delete undone")
    c = m.Buffer()
    for ch in "ab":
        c.insert(len(c.text), ch)
    c.undo()
    c.redo()
    c.insert(2, "c")
    expect(c.undo(), True, "undo after redo")
    expect(c.text, "ab", "insert after redo starts a new group")


@check
def new_edit_clears_redo():
    b = buf_mod().Buffer("x")
    b.insert(1, "yy")
    b.undo()
    expect(b.text, "x", "after undo")
    b.insert(0, "z")
    expect(b.redo(), False, "redo cleared by new edit")
    expect(b.text, "zx", "text")


@check
def typing_coalesces():
    b = buf_mod().Buffer()
    for ch in "hello":
        b.insert(len(b.text), ch)
    expect(b.text, "hello", "typed")
    expect(b.undo(), True, "one undo")
    expect(b.text, "", "one group")
    expect(b.undo(), False, "no second group")


@check
def word_boundary_breaks_group():
    b = buf_mod().Buffer()
    for ch in "hello world":
        b.insert(len(b.text), ch)
    b.undo()
    expect(b.text, "hello ", "first undo removes world")
    b.undo()
    expect(b.text, "", "second undo removes hello")


@check
def max_undo_limit():
    m = buf_mod()
    b = m.Buffer(max_undo=2)
    b.insert(0, "aa")
    b.insert(2, "bb")
    b.insert(4, "cc")
    expect(b.undo(), True, "undo 1")
    expect(b.undo(), True, "undo 2")
    expect(b.undo(), False, "oldest group dropped")
    expect(b.text, "aa", "first insert kept")
    raises(ValueError, m.Buffer, "", 0)


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
