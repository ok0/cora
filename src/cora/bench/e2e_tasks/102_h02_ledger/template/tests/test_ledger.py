from ledger import Book, Entry, format_cents, load_lines, monthly_summary, parse_amount


def _raises(exc, fn, *args):
    try:
        fn(*args)
    except exc as e:
        return e
    raise AssertionError(f"{exc.__name__} not raised")


def _book():
    book = Book()
    book.add(Entry("2024-01-05", "food", 1250, "lunch"))
    book.add(Entry("2024-01-07", "food", -300))
    book.add(Entry("2024-02-01", "rent", 90000))
    return book


def test_parse_amount():
    assert parse_amount("12.30") == 1230
    assert parse_amount("-0.05") == -5
    assert parse_amount("7") == 700
    assert "bad amount" in str(_raises(ValueError, parse_amount, "12.3"))


def test_balance():
    book = _book()
    assert book.balance("food") == 950
    assert book.balance("rent") == 90000
    assert book.balance("unknown") == 0
    assert book.balances() == {"food": 950, "rent": 90000}


def test_format_cents():
    assert format_cents(-1230) == "-12.30"
    assert format_cents(5) == "0.05"
    assert format_cents(123456) == "1,234.56"
    assert format_cents(0) == "0.00"


def test_monthly_summary():
    book = _book()
    assert monthly_summary(book, "food") == [("2024-01", 950)]
    assert monthly_summary(book, "rent") == [("2024-02", 90000)]


def test_load_lines():
    lines = [
        "# imported 2024-02",
        "",
        "2024-01-05;food;12.50;lunch",
        "2024-01-07;food;-3.00;",
        "2024-02-01;rent;900;",
    ]
    book = load_lines(lines)
    assert book.entries() == [
        Entry("2024-01-05", "food", 1250, "lunch"),
        Entry("2024-01-07", "food", -300, ""),
        Entry("2024-02-01", "rent", 90000, ""),
    ]
    assert book.balance("food") == 950
    err = _raises(ValueError, load_lines, ["", "# c", "2024-01-05;food;1.00"])
    assert str(err) == "line 3: expected 4 fields"
