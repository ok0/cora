"""Message id helpers.

Ids are short lowercase hexadecimal strings. They are derived from a sequence
number and a salt so that ids are stable for a given input and never empty.
"""

import hashlib

ID_LENGTH = 12


def make_id(sequence, salt=""):
    """Return a stable id for ``sequence`` and ``salt``."""
    if sequence < 0:
        raise ValueError("sequence must not be negative")
    digest = hashlib.sha256(f"{salt}:{sequence}".encode("utf-8")).hexdigest()
    return digest[:ID_LENGTH]


def is_valid_id(value):
    """Return True when ``value`` looks like an id produced by ``make_id``."""
    if not isinstance(value, str) or len(value) != ID_LENGTH:
        return False
    return all(ch in "0123456789abcdef" for ch in value)
