"""JSON helpers for messages that are written to the spool or printed.

Messages are plain dicts. ``canonical`` gives the same text for equal messages, which
the storage layer relies on when it compares a stored copy with a new one.
"""

import json


def canonical(value):
    """Return a canonical JSON string for ``value`` with sorted keys and no spaces."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse(text):
    """Parse a JSON object from ``text``. Non-object JSON raises ValueError."""
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("message must be a JSON object")
    return value
