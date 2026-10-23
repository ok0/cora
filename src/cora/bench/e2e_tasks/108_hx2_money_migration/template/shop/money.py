"""Exact money helpers: decimal rounding to cents and two-decimal text output."""

from decimal import ROUND_HALF_UP, Decimal


def quantize(value) -> Decimal:
    """Return ``value`` as a Decimal rounded half-up to cents."""
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def fmt(d: Decimal) -> str:
    """Render a Decimal with exactly two decimals."""
    return f"{d:.2f}"
