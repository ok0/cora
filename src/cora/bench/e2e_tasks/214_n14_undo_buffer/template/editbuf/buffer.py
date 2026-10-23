"""Text buffer with undo and redo."""


class Buffer:
    def __init__(self, text: str = "", max_undo: int = 100) -> None:
        """Start with text and no undo history. Raise ValueError if max_undo < 1."""
        raise NotImplementedError

    @property
    def text(self) -> str:
        """The current text."""
        raise NotImplementedError

    def insert(self, pos: int, s: str) -> None:
        """Insert s at pos. Raise IndexError unless 0 <= pos <= len(text). An empty s is a no-op."""
        raise NotImplementedError

    def delete(self, pos: int, n: int) -> None:
        """Delete n characters at pos.

        Raise IndexError unless pos >= 0, n >= 0 and pos + n <= len(text). n == 0 is a no-op.
        """
        raise NotImplementedError

    def undo(self) -> bool:
        """Revert the latest undo group. Return False if there is none."""
        raise NotImplementedError

    def redo(self) -> bool:
        """Re-apply the most recently undone group. Return False if there is none."""
        raise NotImplementedError
