"""Invoice text. Each line is a ``(name, price, qty)`` triple followed by a TOTAL line."""

from shop.compat import round_money


def render_invoice(lines) -> str:
    """Return one line per item and a final TOTAL line, rounded to cents."""
    out = []
    total = 0.0
    for name, price, qty in lines:
        amount = round_money(float(price) * qty)
        total += amount
        out.append(f"{name}: {amount}")
    out.append(f"TOTAL: {round_money(total)}")
    return "\n".join(out)
