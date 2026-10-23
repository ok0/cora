def column_stats(rows: list[list[str]], column: str) -> dict:
    header = rows[0]
    if column not in header:
        raise KeyError(column)
    index = header.index(column)
    values: list[float] = []
    for row in rows[1:]:
        cell = row[index]
        if cell == "":
            continue
        try:
            values.append(float(cell))
        except ValueError:
            raise ValueError(f"non-numeric value {cell!r} in column {column!r}") from None
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 2),
    }
