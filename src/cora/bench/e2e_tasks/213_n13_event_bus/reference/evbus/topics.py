"""Topic and pattern syntax."""

import re

SEGMENT = re.compile(r"[a-z0-9_]+")


def validate_topic(t: str) -> None:
    """Raise ValueError(f"bad topic '{t}'") unless t is a valid topic."""
    if not all(SEGMENT.fullmatch(seg) for seg in t.split(".")):
        raise ValueError(f"bad topic '{t}'")


def validate_pattern(p: str) -> None:
    """Raise ValueError(f"bad pattern '{p}'") unless p is a valid pattern."""
    segs = p.split(".")
    for i, seg in enumerate(segs):
        if seg == "#":
            if i != len(segs) - 1:
                raise ValueError(f"bad pattern '{p}'")
        elif seg != "*" and not SEGMENT.fullmatch(seg):
            raise ValueError(f"bad pattern '{p}'")


def matches(pattern: str, topic: str) -> bool:
    """Return True if the pattern matches the topic."""
    return _match(pattern.split("."), topic.split("."))


def _match(p: list[str], t: list[str]) -> bool:
    if not p:
        return not t
    if p[0] == "#":
        return True
    if not t:
        return False
    if p[0] == "*" or p[0] == t[0]:
        return _match(p[1:], t[1:])
    return False
