"""Loyalty tiers by lifetime points."""

TIERS = ((0, "bronze"), (500, "silver"), (2000, "gold"))


def tier_for(points: int) -> str:
    """Return the highest tier whose threshold the points reach."""
    name = TIERS[0][1]
    for threshold, label in TIERS:
        if points >= threshold:
            name = label
    return name
