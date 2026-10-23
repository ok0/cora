from .model import Shift, Staff


def can_take(staff: Staff, shift: Shift, assigned: list[Shift]) -> str | None:
    """Return the first failing reason ("unavailable", "overlap", "rest", "hours") or None if the staff member can take the shift."""
    raise NotImplementedError
