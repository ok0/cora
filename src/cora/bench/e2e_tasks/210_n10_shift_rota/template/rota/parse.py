from .model import Shift


def parse_shift(id: str, text: str) -> Shift:
    """Parse "Mon 22:00-06:00" into a Shift with the given id. Raise ValueError(f"bad shift '{text}'") if invalid."""
    raise NotImplementedError


def parse_unavailable(text: str) -> tuple[int, int, int]:
    """Parse "Sat" or "Mon 09:00-12:00" into (day, start, end) in minutes. Raise ValueError(f"bad unavailability '{text}'") if invalid."""
    raise NotImplementedError
