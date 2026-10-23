# Refactor: inventory package

`inventory.py` works but is a single module that passes dicts around and computes the
total twice. Refactor it without changing behaviour:

1. Replace the module `inventory.py` with a package `inventory/` and delete `inventory.py`.
   `inventory/__init__.py` must export `Item`, `total_value`, `report` and `low_stock`
   (`from inventory import Item, total_value, report, low_stock`).
2. Add `Item` in `inventory/models.py`: a frozen dataclass with fields `name: str`,
   `qty: int`, `price: float` (in this order) and a classmethod `Item.from_dict(d: dict)`
   that reads the keys `name`, `qty` and `price`.
3. `total_value(items)`, `report(items)` and `low_stock(items, limit)` take a list of `Item`
   and keep their current results (same strings, same order). Put them in `inventory/core.py`.
4. `report` must not repeat the total computation: it must call `total_value`.
5. Update `test_inventory.py` to build `Item` objects (`Item(...)` or `Item.from_dict(...)`);
   `python test_inventory.py` must exit 0.
