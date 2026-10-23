"""Todo CLI - reference solution (tests only)."""

import json
import os
import sys

DATA = "todo.json"
USAGE = "usage: todo.py add TEXT | list | done ID | remove ID"


def load() -> list[dict]:
    if not os.path.exists(DATA):
        return []
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def save(items: list[dict]) -> None:
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(items, f)


def find(items: list[dict], raw: str) -> dict | None:
    try:
        wanted = int(raw)
    except ValueError:
        return None
    for item in items:
        if item["id"] == wanted:
            return item
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    items = load()
    if cmd == "add" and len(args) == 1:
        new_id = max((i["id"] for i in items), default=0) + 1
        items.append({"id": new_id, "text": args[0], "done": False})
        save(items)
        print(f"added {new_id}: {args[0]}")
        return 0
    if cmd == "list" and not args:
        if not items:
            print("no items")
        for item in items:
            mark = "x" if item["done"] else " "
            print(f"{item['id']} [{mark}] {item['text']}")
        return 0
    if cmd in ("done", "remove") and len(args) == 1:
        item = find(items, args[0])
        if item is None:
            print(f"error: no item {args[0]}", file=sys.stderr)
            return 1
        if cmd == "done":
            item["done"] = True
            print(f"done {item['id']}")
        else:
            items.remove(item)
            print(f"removed {item['id']}")
        save(items)
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
