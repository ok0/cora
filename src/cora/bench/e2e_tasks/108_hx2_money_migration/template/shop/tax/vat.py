"""VAT amounts: the net amount multiplied by a rate given as a fraction, e.g. ``"0.2"``."""

from shop.compat import round_money


def vat_amount(net, rate) -> float:
    """Return the VAT due on ``net`` at ``rate``, rounded to cents."""
    return round_money(float(net) * float(rate))
