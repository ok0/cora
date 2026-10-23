from .models import Student, WEIGHTS


def weighted_average(student: Student) -> float:
    """Return the weighted average of the student's scores, rounded to 2 decimals."""
    total = sum(weight * student.scores.get(category, 0) for category, weight in WEIGHTS.items())
    return round(total, 2)


def letter(avg: float) -> str:
    """Return the letter grade for an average from 0 to 100."""
    if avg < 0 or avg > 100:
        raise ValueError(f"score out of range: {avg}")
    if avg >= 90:
        return "A"
    if avg >= 80:
        return "B"
    if avg >= 70:
        return "C"
    if avg >= 60:
        return "D"
    return "F"


def rank(students: list[Student]) -> list[tuple[str, float, str]]:
    """Return (name, avg, letter) tuples sorted by avg descending, then name ascending."""
    rows = []
    for student in students:
        avg = weighted_average(student)
        rows.append((student.name, avg, letter(avg)))
    return sorted(rows, key=lambda row: (-row[1], row[0]))
