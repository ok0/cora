def resolve(
    merged: dict[str, dict[str, tuple[str, str]]],
) -> dict[str, dict[str, tuple[str, str]]]:
    """Interpolate every merged value and keep its source."""
    raise NotImplementedError
