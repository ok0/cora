"""VAT amounts: the net amount multiplied by a rate given as a fraction, e.g. ``"0.2"``."""

from decimal import Decimal

from shop.money import quantize


def vat_amount(net, rate) -> Decimal:
    """Return the VAT due on ``net`` at ``rate``, rounded to cents."""
    return quantize(Decimal(str(net)) * Decimal(str(rate)))
