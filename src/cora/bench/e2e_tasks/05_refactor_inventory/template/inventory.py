def total_value(items):
    t = 0
    for i in items:
        t = t + i["qty"] * i["price"]
    return t


def report(items):
    lines = []
    for i in items:
        lines.append(i["name"] + ": " + str(i["qty"]) + " x " + "%.2f" % i["price"])
    t = 0
    for i in items:
        t = t + i["qty"] * i["price"]
    lines.append("TOTAL: " + "%.2f" % t)
    return "\n".join(lines)


def low_stock(items, limit):
    out = []
    for i in items:
        if i["qty"] < limit:
            out.append(i["name"])
    return out
