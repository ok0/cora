"""Text buffer with undo and redo."""

from .history import Edit, History


class Buffer:
    def __init__(self, text: str = "", max_undo: int = 100) -> None:
        """Start with text and no undo history. Raise ValueError if max_undo < 1."""
        if max_undo < 1:
            raise ValueError("max_undo must be >= 1")
        self._text = text
        self._hist = History(max_undo)

    @property
    def text(self) -> str:
        """The current text."""
        return self._text

    def insert(self, pos: int, s: str) -> None:
        """Insert s at pos. Raise IndexError unless 0 <= pos <= len(text). An empty s is a no-op."""
        if not 0 <= pos <= len(self._text):
            raise IndexError(f"insert position {pos} out of range")
        if s == "":
            return
        last = self._hist.last()
        join = (
            len(s) == 1
            and last is not None
            and last.kind == "insert"
            and last.pos + len(last.text) == pos
            and last.text[-1] not in " \n"
        )
        self._text = self._text[:pos] + s + self._text[pos:]
        self._hist.push(Edit("insert", pos, s), join)

    def delete(self, pos: int, n: int) -> None:
        """Delete n characters at pos.

        Raise IndexError unless pos >= 0, n >= 0 and pos + n <= len(text). n == 0 is a no-op.
        """
        if pos < 0 or n < 0 or pos + n > len(self._text):
            raise IndexError(f"delete range {pos}+{n} out of range")
        if n == 0:
            return
        removed = self._text[pos:pos + n]
        self._text = self._text[:pos] + self._text[pos + n:]
        self._hist.push(Edit("delete", pos, removed), False)

    def undo(self) -> bool:
        """Revert the latest undo group. Return False if there is none."""
        group = self._hist.undo_group()
        if group is None:
            return False
        for e in reversed(group):
            if e.kind == "insert":
                self._text = self._text[:e.pos] + self._text[e.pos + len(e.text):]
            else:
                self._text = self._text[:e.pos] + e.text + self._text[e.pos:]
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone group. Return False if there is none."""
        group = self._hist.redo_group()
        if group is None:
            return False
        for e in group:
            if e.kind == "insert":
                self._text = self._text[:e.pos] + e.text + self._text[e.pos:]
            else:
                self._text = self._text[:e.pos] + self._text[e.pos + len(e.text):]
        return True
