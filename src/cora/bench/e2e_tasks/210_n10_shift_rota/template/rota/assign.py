from .model import Rota, Shift, Staff


def assign(shifts: list[Shift], staff: list[Staff]) -> Rota:
    """Assign each shift to one staff member, or None if unfilled. Return the Rota."""
    raise NotImplementedError
