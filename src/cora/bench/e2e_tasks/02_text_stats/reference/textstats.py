"""Text statistics - reference solution (tests only)."""

import re
from collections import Counter

WORD = re.compile(r"[A-Za-z0-9']+")


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text)]


def word_count(text: str) -> int:
    return len(_words(text))


def char_frequency(text: str) -> dict[str, int]:
    return dict(Counter(c for c in text.lower() if "a" <= c <= "z"))


def top_words(text: str, n: int) -> list[tuple[str, int]]:
    if n <= 0:
        return []
    ranked = sorted(Counter(_words(text)).items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:n]


def average_word_length(text: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    return round(sum(len(w) for w in words) / len(words), 2)


def sentence_count(text: str) -> int:
    if not WORD.search(text):
        return 0
    parts = re.split(r"[.!?]+", text)
    count = len(parts) - 1
    if WORD.search(parts[-1]):
        count += 1
    return count
