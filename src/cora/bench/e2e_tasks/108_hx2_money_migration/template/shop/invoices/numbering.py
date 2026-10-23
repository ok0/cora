"""Sequential invoice numbers of the form INV-000001."""


def next_number(last: int) -> str:
    """Return the invoice number that follows ``last``."""
    return f"INV-{last + 1:06d}"
