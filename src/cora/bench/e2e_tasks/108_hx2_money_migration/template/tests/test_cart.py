from decimal import Decimal

from shop.cart.totals import cart_total, line_total


def test_totals():
    assert line_total("2.675", 1) == Decimal("2.68")
    assert cart_total([("2.675", 1), ("1.00", 2)]) == Decimal("4.68")
