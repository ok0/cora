def parse(text: str) -> dict[str, dict[str, tuple[str, int]]]:
    """Parse configuration text into section -> key -> (raw value, 1-based line)."""
    raise NotImplementedError
