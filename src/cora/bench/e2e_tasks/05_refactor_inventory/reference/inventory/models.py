"""Inventory data model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    name: str
    qty: int
    price: float

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(d["name"], d["qty"], d["price"])
