from .book import Book
from .models import Entry, parse_amount


def load_lines(lines: list[str]) -> Book:
    book = Book()
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) != 4:
            raise ValueError(f"line {number}: expected 4 fields")
        date, account, amount, memo = fields
        book.add(Entry(date, account, parse_amount(amount), memo))
    return book
