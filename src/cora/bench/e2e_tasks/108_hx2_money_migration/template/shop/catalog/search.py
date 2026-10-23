"""Case-insensitive product search by name."""

from shop.catalog.products import Product


def search(products, term: str) -> list[Product]:
    """Return the products whose name contains ``term``, ignoring case and outer spaces."""
    needle = term.strip().lower()
    return [p for p in products if needle in p.name.lower()]
