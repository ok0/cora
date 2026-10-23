"""Text statistics - see REQUIREMENTS.md."""


def word_count(text: str) -> int:
    raise NotImplementedError


def char_frequency(text: str) -> dict[str, int]:
    raise NotImplementedError


def top_words(text: str, n: int) -> list[tuple[str, int]]:
    raise NotImplementedError


def average_word_length(text: str) -> float:
    raise NotImplementedError


def sentence_count(text: str) -> int:
    raise NotImplementedError
