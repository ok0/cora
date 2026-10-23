"""Eligibility rules for discounts."""


def is_eligible(subtotal, minimum) -> bool:
    """Return True when the subtotal reaches the minimum order value."""
    return float(subtotal) >= float(minimum)
