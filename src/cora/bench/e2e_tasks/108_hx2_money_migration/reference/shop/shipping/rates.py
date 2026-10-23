"""Shipping costs: weight in kilograms times the per-kilogram rate of the zone."""

from decimal import Decimal

from shop.money import quantize

RATES = {"local": "1.20", "eu": "2.35", "world": "3.90"}


def shipping_cost(weight_kg, zone: str) -> Decimal:
    """Return the shipping cost for a parcel of ``weight_kg`` sent to ``zone``."""
    return quantize(Decimal(str(weight_kg)) * Decimal(RATES[zone]))
