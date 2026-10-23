from .models import Student


def weighted_average(student: Student) -> float:
    """Return the weighted average of the student's scores, rounded to 2 decimals."""
    raise NotImplementedError


def letter(avg: float) -> str:
    """Return the letter grade for an average from 0 to 100."""
    raise NotImplementedError


def rank(students: list[Student]) -> list[tuple[str, float, str]]:
    """Return (name, avg, letter) tuples sorted by avg descending, then name ascending."""
    raise NotImplementedError
