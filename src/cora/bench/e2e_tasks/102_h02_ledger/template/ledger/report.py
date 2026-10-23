from .book import Book


def monthly_summary(book: Book, account: str) -> list[tuple[str, int]]:
    raise NotImplementedError


def format_cents(n: int) -> str:
    raise NotImplementedError
