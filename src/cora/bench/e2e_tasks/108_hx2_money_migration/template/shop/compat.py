"""Older money helpers kept for other projects that still import them."""

import warnings


def round_money(x: float) -> float:
    """Round a float to two decimals. Deprecated: use ``shop.money.quantize``."""
    warnings.warn("round_money is deprecated; use quantize", DeprecationWarning, stacklevel=2)
    return round(float(x), 2)
