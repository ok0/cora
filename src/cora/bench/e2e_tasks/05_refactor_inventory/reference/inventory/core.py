"""Inventory calculations."""

from inventory.models import Item


def total_value(items: list[Item]) -> float:
    return sum(i.qty * i.price for i in items)


def report(items: list[Item]) -> str:
    lines = [f"{i.name}: {i.qty} x {i.price:.2f}" for i in items]
    lines.append(f"TOTAL: {total_value(items):.2f}")
    return "\n".join(lines)


def low_stock(items: list[Item], limit: int) -> list[str]:
    return [i.name for i in items if i.qty < limit]
