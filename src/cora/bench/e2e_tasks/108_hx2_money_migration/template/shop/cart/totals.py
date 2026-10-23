"""Line and cart totals. A line is a ``(price, qty)`` pair; price may be str, int or Decimal."""

from shop.compat import round_money


def line_total(price, qty: int) -> float:
    """Return the total of one line, rounded to cents."""
    return round_money(float(price) * qty)


def cart_total(lines) -> float:
    """Return the sum of the line totals of ``lines``."""
    return sum((line_total(price, qty) for price, qty in lines), 0.0)
