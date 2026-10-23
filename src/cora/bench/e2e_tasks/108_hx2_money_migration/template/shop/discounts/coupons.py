"""Percentage coupons: the amount left after a percentage discount."""

from shop.compat import round_money


def apply_percent(amount, percent) -> float:
    """Return ``amount`` after taking ``percent`` percent off, rounded to cents."""
    return round_money(float(amount) * (1 - float(percent) / 100))
