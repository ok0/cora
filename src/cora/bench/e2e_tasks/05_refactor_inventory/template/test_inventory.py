"""Tests for inventory. Run: python test_inventory.py"""

from inventory import low_stock, report, total_value

ITEMS = [
    {"name": "bolt", "qty": 3, "price": 0.5},
    {"name": "nut", "qty": 10, "price": 0.1},
]


def test_total_value():
    assert abs(total_value(ITEMS) - 2.5) < 1e-9


def test_report():
    assert report(ITEMS) == "bolt: 3 x 0.50\nnut: 10 x 0.10\nTOTAL: 2.50"


def test_low_stock():
    assert low_stock(ITEMS, 5) == ["bolt"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
