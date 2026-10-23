"""Loyalty points: each point is worth a fixed decimal amount."""

from decimal import Decimal

from shop.money import quantize

POINT_VALUE = Decimal("0.005")


def points_value(points) -> Decimal:
    """Return the monetary value of ``points``, rounded to cents."""
    return quantize(Decimal(str(points)) * POINT_VALUE)
