class Config:
    """Typed read access to resolved configuration values."""

    def __init__(self, data: dict[str, dict[str, tuple[str, str]]]) -> None:
        """Keep the resolved section -> key -> (value, source) data."""
        raise NotImplementedError

    def get(self, section: str, key: str) -> str:
        """Return the resolved string value."""
        raise NotImplementedError

    def get_int(self, section: str, key: str) -> int:
        """Return the value as an integer."""
        raise NotImplementedError

    def get_bool(self, section: str, key: str) -> bool:
        """Return the value as a boolean."""
        raise NotImplementedError

    def get_list(self, section: str, key: str) -> list[str]:
        """Return the value split into a list of items."""
        raise NotImplementedError

    def source(self, section: str, key: str) -> str:
        """Return where the value came from."""
        raise NotImplementedError
