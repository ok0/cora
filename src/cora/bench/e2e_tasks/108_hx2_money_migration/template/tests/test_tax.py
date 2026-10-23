from decimal import Decimal

from shop.tax.vat import vat_amount


def test_vat():
    assert vat_amount("2.15", "0.1") == Decimal("0.22")
