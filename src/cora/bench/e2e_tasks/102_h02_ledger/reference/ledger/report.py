from .book import Book


def monthly_summary(book: Book, account: str) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for e in book.entries():
        if e.account == account:
            month = e.date[:7]
            totals[month] = totals.get(month, 0) + e.amount_cents
    return sorted(totals.items())


def format_cents(n: int) -> str:
    sign = "-" if n < 0 else ""
    whole, frac = divmod(abs(n), 100)
    return f"{sign}{whole:,}.{frac:02d}"
