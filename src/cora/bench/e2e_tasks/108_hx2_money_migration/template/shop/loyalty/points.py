"""Loyalty points: each point is worth a fixed decimal amount."""

from shop.compat import round_money

POINT_VALUE = 0.005


def points_value(points) -> float:
    """Return the monetary value of ``points``, rounded to cents."""
    return round_money(points * POINT_VALUE)
