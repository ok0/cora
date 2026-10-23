from gradebook import Student, letter, weighted_average


def test_weighted_average_basic():
    student = Student("ann", {"homework": 90, "midterm": 80, "final": 85})
    assert weighted_average(student) == 85.0


def test_letter_simple():
    assert letter(85.0) == "B"
