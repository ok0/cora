"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import hashlib
import importlib
import json
import os
import sys

ROOT = os.getcwd()
CHECKS = []
SPEC_SHA256 = "0636cf985bd9ebece79e15665f12e0ed7c37a9dce495ae628f710e0a710b6676"
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


def lg():
    return importlib.import_module("ledger")


@check
def parse_amount():
    pa = lg().parse_amount
    expect(pa("12.30"), 1230, "12.30")
    expect(pa("-0.05"), -5, "-0.05")
    expect(pa("7"), 700, "7")
    expect(pa("-7"), -700, "-7")
    expect(pa("0.00"), 0, "0.00")
    expect(pa("1234.56"), 123456, "1234.56")
    for bad in ["12.3", "1.234", "+5", "1,000", "abc", "", "-", "1.", ".50"]:
        e = raises(ValueError, pa, bad)
        expect(str(e), f"bad amount: {bad!r}", f"message for {bad!r}")


@check
def balance():
    m = lg()
    b = m.Book()
    b.add(m.Entry("2024-01-05", "food", 1250, "lunch"))
    b.add(m.Entry("2024-01-07", "food", -300))
    b.add(m.Entry("2024-02-01", "rent", 90000))
    expect(b.balance("food"), 950, "food")
    expect(b.balance("rent"), 90000, "rent")
    expect(b.balance("nothing"), 0, "unseen account")


@check
def balances():
    m = lg()
    b = m.Book()
    expect(b.balances(), {}, "empty book")
    b.add(m.Entry("2024-01-05", "food", 1250, "lunch"))
    b.add(m.Entry("2024-01-07", "food", -300))
    b.add(m.Entry("2024-02-01", "rent", 90000))
    expect(b.balances(), {"food": 950, "rent": 90000}, "balances")
    expect(list(b.balances().keys()), ["food", "rent"], "sorted keys")
    b.add(m.Entry("2024-03-01", "alpha", 1, ""))
    expect(list(b.balances().keys()), ["alpha", "food", "rent"], "sorted keys after add")


@check
def format_cents():
    fc = lg().format_cents
    expect(fc(-1230), "-12.30", "-1230")
    expect(fc(5), "0.05", "5")
    expect(fc(123456), "1,234.56", "123456")
    expect(fc(0), "0.00", "0")
    expect(fc(-5), "-0.05", "-5")
    expect(fc(100), "1.00", "100")
    expect(fc(1000000), "10,000.00", "1000000")
    expect(fc(-123456789), "-1,234,567.89", "-123456789")


@check
def monthly_summary():
    m = lg()
    b = m.Book()
    b.add(m.Entry("2024-01-05", "food", 1250, "lunch"))
    b.add(m.Entry("2024-01-07", "food", -300))
    b.add(m.Entry("2024-02-01", "rent", 90000))
    expect(m.monthly_summary(b, "food"), [("2024-01", 950)], "food")
    expect(m.monthly_summary(b, "rent"), [("2024-02", 90000)], "rent")
    expect(m.monthly_summary(b, "nothing"), [], "unseen account")
    b.add(m.Entry("2024-01-20", "food", 100, ""))
    b.add(m.Entry("2023-12-31", "food", -50, ""))
    expect(m.monthly_summary(b, "food"), [("2023-12", -50), ("2024-01", 1050)], "sorted by month")


@check
def load_lines():
    m = lg()
    book = m.load_lines([
        "# c",
        "",
        "2024-01-05;food;12.50;lunch",
        "2024-01-07;food;-3.00;",
        "2024-02-01;rent;900;",
    ])
    expect(book.entries(), [
        m.Entry("2024-01-05", "food", 1250, "lunch"),
        m.Entry("2024-01-07", "food", -300, ""),
        m.Entry("2024-02-01", "rent", 90000, ""),
    ], "entries")
    expect(m.load_lines(["  2024-01-05;food;1.00;x  "]).entries(),
           [m.Entry("2024-01-05", "food", 100, "x")], "surrounding whitespace")
    e = raises(ValueError, m.load_lines, ["", "# c", "2024-01-05;food;1.00"])
    expect(str(e), "line 3: expected 4 fields", "field count message")
    e = raises(ValueError, m.load_lines, ["2024-01-05;food;1.00;a;b"])
    expect(str(e), "line 1: expected 4 fields", "too many fields")
    e = raises(ValueError, m.load_lines, ["2024-01-05;food;1.5;x"])
    expect(str(e), "bad amount: '1.5'", "bad amount")


@check
def spec_unchanged():
    with open(os.path.join(ROOT, "tests", "test_ledger.py"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    expect(digest, SPEC_SHA256, "tests/test_ledger.py sha256")


@check
def book_entries_kept():
    m = lg()
    b = m.Book()
    e1 = m.Entry("2024-01-01", "a", 1, "x")
    e2 = m.Entry("2024-01-02", "b", 2, "")
    b.add(e1)
    b.add(e2)
    expect(b.entries(), [e1, e2], "insertion order")


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
