def merge(
    defaults: dict[str, dict[str, str]],
    parsed: dict[str, dict[str, tuple[str, int]]],
    env: dict[str, str],
) -> dict[str, dict[str, tuple[str, str]]]:
    """Merge defaults, file values and environment overrides into section -> key -> (raw value, source)."""
    raise NotImplementedError
