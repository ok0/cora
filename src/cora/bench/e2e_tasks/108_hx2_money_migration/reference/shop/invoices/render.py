"""Invoice text. Each line is a ``(name, price, qty)`` triple followed by a TOTAL line."""

from decimal import Decimal

from shop.money import fmt, quantize


def render_invoice(lines) -> str:
    """Return one line per item and a final TOTAL line, rounded to cents."""
    out = []
    total = Decimal("0")
    for name, price, qty in lines:
        amount = quantize(Decimal(str(price)) * qty)
        total += amount
        out.append(f"{name}: {fmt(amount)}")
    out.append(f"TOTAL: {fmt(total)}")
    return "\n".join(out)
