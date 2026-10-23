def parse_csv(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    row: list[str] = []
    field: list[str] = []
    has_content = False
    in_quotes = False
    quote_line = 0
    line = 1
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_quotes = False
            else:
                if ch == "\n":
                    line += 1
                field.append(ch)
        elif ch == '"':
            in_quotes = True
            quote_line = line
            has_content = True
        elif ch == ",":
            row.append("".join(field))
            field = []
            has_content = True
        elif ch == "\n" or (ch == "\r" and text[i + 1 : i + 2] == "\n"):
            if ch == "\r":
                i += 1
            if has_content:
                row.append("".join(field))
                rows.append(row)
            row = []
            field = []
            has_content = False
            line += 1
        else:
            field.append(ch)
            has_content = True
        i += 1
    if in_quotes:
        raise ValueError(f"unterminated quote at line {quote_line}")
    if has_content:
        row.append("".join(field))
        rows.append(row)
    return rows
