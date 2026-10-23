from dataclasses import dataclass

WEIGHTS = {"homework": 0.3, "midterm": 0.3, "final": 0.4}


@dataclass
class Student:
    name: str
    scores: dict[str, float]
