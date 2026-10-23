"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import ast
import dataclasses
import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


@check
def package_layout():
    assert os.path.isfile(os.path.join(ROOT, "inventory", "__init__.py")), \
        "inventory/__init__.py missing"
    assert not os.path.exists(os.path.join(ROOT, "inventory.py")), "inventory.py still exists"
    inv = importlib.import_module("inventory")
    for name in ("Item", "total_value", "report", "low_stock"):
        assert hasattr(inv, name), f"missing export {name}"


@check
def item_dataclass():
    Item = importlib.import_module("inventory").Item
    assert dataclasses.is_dataclass(Item), "Item is not a dataclass"
    expect([f.name for f in dataclasses.fields(Item)], ["name", "qty", "price"], "fields")
    expect(Item.from_dict({"name": "a", "qty": 1, "price": 2.0}), Item("a", 1, 2.0), "from_dict")
    item = Item("a", 1, 2.0)
    try:
        item.qty = 5
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Item is not frozen")


@check
def behaviour_preserved():
    inv = importlib.import_module("inventory")
    items = [inv.Item("bolt", 3, 0.5), inv.Item("nut", 10, 0.1)]
    assert abs(inv.total_value(items) - 2.5) < 1e-9, "total_value"
    expect(inv.report(items), "bolt: 3 x 0.50\nnut: 10 x 0.10\nTOTAL: 2.50", "report")
    expect(inv.low_stock(items, 5), ["bolt"], "low_stock")
    expect(inv.low_stock([], 5), [], "low_stock empty")


@check
def report_uses_total_value():
    found = False
    uses = False
    for name in sorted(os.listdir(os.path.join(ROOT, "inventory"))):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ROOT, "inventory", name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "report":
                found = True
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        func = sub.func
                        if (isinstance(func, ast.Name) and func.id == "total_value") or (
                            isinstance(func, ast.Attribute) and func.attr == "total_value"
                        ):
                            uses = True
    assert found, "no report function in inventory/"
    assert uses, "report does not call total_value"


@check
def tests_updated():
    with open(os.path.join(ROOT, "test_inventory.py"), encoding="utf-8") as f:
        source = f.read()
    assert "Item(" in source or "Item.from_dict(" in source, "test_inventory.py does not use Item"
    proc = subprocess.run([sys.executable, "-B", "test_inventory.py"], cwd=ROOT,
                          capture_output=True, text=True, timeout=30)
    expect(proc.returncode, 0, "python test_inventory.py exit code")


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
