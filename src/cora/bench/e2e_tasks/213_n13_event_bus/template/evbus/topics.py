"""Topic and pattern syntax."""


def validate_topic(t: str) -> None:
    """Raise ValueError(f"bad topic '{t}'") unless t is a valid topic."""
    raise NotImplementedError


def validate_pattern(p: str) -> None:
    """Raise ValueError(f"bad pattern '{p}'") unless p is a valid pattern."""
    raise NotImplementedError


def matches(pattern: str, topic: str) -> bool:
    """Return True if the pattern matches the topic."""
    raise NotImplementedError
