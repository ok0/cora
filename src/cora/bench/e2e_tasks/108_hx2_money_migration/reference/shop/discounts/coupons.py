"""Percentage coupons: the amount left after a percentage discount."""

from decimal import Decimal

from shop.money import quantize


def apply_percent(amount, percent) -> Decimal:
    """Return ``amount`` after taking ``percent`` percent off, rounded to cents."""
    factor = (Decimal("100") - Decimal(str(percent))) / Decimal("100")
    return quantize(Decimal(str(amount)) * factor)
