"""Test specification for textstats. Run: python test_textstats.py"""

from textstats import (
    average_word_length,
    char_frequency,
    sentence_count,
    top_words,
    word_count,
)


def test_word_count():
    assert word_count("Hello, world! It's 2024.") == 4
    assert word_count("") == 0


def test_char_frequency():
    assert char_frequency("Aab!") == {"a": 2, "b": 1}


def test_top_words():
    assert top_words("b a b c a b", 2) == [("b", 3), ("a", 2)]


def test_average_word_length():
    assert average_word_length("ab abcd") == 3.0


def test_sentence_count():
    assert sentence_count("One. Two!") == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("ok")
