"""Calendar helpers for order and invoice dates."""

from datetime import date, timedelta


def add_days(day: date, days: int) -> date:
    """Return the date ``days`` days after ``day``."""
    return day + timedelta(days=days)


def is_weekend(day: date) -> bool:
    """Return True when the date falls on a Saturday or a Sunday."""
    return day.weekday() >= 5
