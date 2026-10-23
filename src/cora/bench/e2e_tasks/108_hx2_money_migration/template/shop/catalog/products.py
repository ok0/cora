"""Product records and an in-memory catalogue keyed by SKU."""

from dataclasses import dataclass

CATALOG: dict = {}


@dataclass(frozen=True)
class Product:
    """One sellable product. ``price`` is a decimal string such as ``"12.50"``."""

    sku: str
    name: str
    price: str
    category: str


def add_product(product: Product) -> None:
    """Store a product, replacing any product with the same SKU."""
    CATALOG[product.sku] = product


def get_product(sku: str) -> Product:
    """Return the product with the given SKU or raise KeyError."""
    return CATALOG[sku]
