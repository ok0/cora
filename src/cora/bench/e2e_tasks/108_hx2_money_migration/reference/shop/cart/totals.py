"""Line and cart totals. A line is a ``(price, qty)`` pair; price may be str, int or Decimal."""

from decimal import Decimal

from shop.money import quantize


def line_total(price, qty: int) -> Decimal:
    """Return the total of one line, rounded to cents."""
    return quantize(Decimal(str(price)) * qty)


def cart_total(lines) -> Decimal:
    """Return the sum of the line totals of ``lines``."""
    return sum((line_total(price, qty) for price, qty in lines), Decimal("0"))
