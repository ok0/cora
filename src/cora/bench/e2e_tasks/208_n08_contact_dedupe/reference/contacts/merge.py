from .normalize import normalize_email


def dedupe(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    kept: list[dict[str, str]] = []
    index: dict[str, int] = {}
    removed = 0
    for row in rows:
        key = normalize_email(row.get("email", ""))
        if key and key in index:
            target = kept[index[key]]
            for field, value in row.items():
                if value and not target.get(field, ""):
                    target[field] = value
            removed += 1
            continue
        if key:
            index[key] = len(kept)
        kept.append(dict(row))
    return kept, removed
