"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import ast
import json
import os
import sys
import warnings
from decimal import Decimal

ROOT = os.getcwd()
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


@check
def no_round_money_uses():
    found = False
    base = os.path.join(ROOT, "shop")
    for dirpath, _dirs, files in os.walk(base):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            if rel == "shop/compat.py":
                continue
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "round_money":
                    found = True
                elif isinstance(node, ast.Attribute) and node.attr == "round_money":
                    found = True
                elif isinstance(node, ast.alias) and node.name == "round_money":
                    found = True
    assert not found, "round_money is still referenced outside shop/compat.py"


def _calls():
    from shop.cart.totals import line_total
    from shop.discounts.coupons import apply_percent
    from shop.invoices.render import render_invoice
    from shop.loyalty.points import points_value
    from shop.shipping.rates import shipping_cost
    from shop.tax.vat import vat_amount
    return [
        lambda: line_total("1.00", 1),
        lambda: vat_amount("1.00", "0.1"),
        lambda: apply_percent("1.00", 10),
        lambda: shipping_cost("1", "local"),
        lambda: render_invoice([("a", "1.00", 1)]),
        lambda: points_value(10),
    ]


@check
def no_deprecation_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        for call in _calls():
            call()


@check
def compat_shim_kept():
    from shop.compat import round_money
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = round_money(2.5)
    expect(value, 2.5, "round_money(2.5)")
    assert any(issubclass(w.category, DeprecationWarning) for w in caught), \
        "round_money does not warn"


@check
def totals():
    from shop.cart.totals import cart_total, line_total
    value = line_total("2.675", 1)
    assert isinstance(value, Decimal), "line_total does not return Decimal"
    expect(value, Decimal("2.68"), "line_total half-up")
    total = cart_total([("2.675", 1), ("1.00", 2)])
    assert isinstance(total, Decimal), "cart_total does not return Decimal"
    expect(total, Decimal("4.68"), "cart_total")


@check
def vat():
    from shop.tax.vat import vat_amount
    value = vat_amount("2.15", "0.1")
    assert isinstance(value, Decimal), "vat_amount does not return Decimal"
    expect(value, Decimal("0.22"), "vat_amount half-up")


@check
def coupons():
    from shop.discounts.coupons import apply_percent
    value = apply_percent("0.15", 50)
    assert isinstance(value, Decimal), "apply_percent does not return Decimal"
    expect(value, Decimal("0.08"), "apply_percent half-up")


@check
def shipping():
    from shop.shipping.rates import shipping_cost
    value = shipping_cost("0.3", "eu")
    assert isinstance(value, Decimal), "shipping_cost does not return Decimal"
    expect(value, Decimal("0.71"), "shipping_cost half-up")


@check
def invoice():
    from shop.invoices.render import render_invoice
    text = render_invoice([("bolt", "2.675", 1)])
    assert isinstance(text, str), "render_invoice does not return str"
    assert "bolt: 2.68" in text, f"item line missing or not half-up: {text!r}"
    assert "TOTAL: 2.68" in text, f"total line missing or not half-up: {text!r}"


@check
def loyalty():
    from shop.loyalty.points import points_value
    value = points_value(25)
    assert isinstance(value, Decimal), "points_value does not return Decimal"
    expect(value, Decimal("0.13"), "points_value half-up")


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
