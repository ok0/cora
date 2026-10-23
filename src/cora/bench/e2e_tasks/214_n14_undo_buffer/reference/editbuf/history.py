"""Undo and redo groups."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Edit:
    kind: str
    pos: int
    text: str


class History:
    def __init__(self, max_groups: int) -> None:
        """Keep at most max_groups undo groups."""
        self._max = max_groups
        self._undo: list[list[Edit]] = []
        self._redo: list[list[Edit]] = []
        self._open = False

    def push(self, edit: Edit, join: bool) -> None:
        """Record an edit.

        With join=True and an open group, append to it; otherwise start a new open group.
        Clear redo and drop the oldest groups beyond max_groups.
        """
        if join and self._open and self._undo:
            self._undo[-1].append(edit)
        else:
            self._undo.append([edit])
            if len(self._undo) > self._max:
                del self._undo[0]
        self._redo.clear()
        self._open = True

    def last(self) -> Edit | None:
        """Return the last edit of the open group, or None if no group is open."""
        if self._open and self._undo:
            return self._undo[-1][-1]
        return None

    def undo_group(self) -> list[Edit] | None:
        """Move the latest group to the redo stack.

        Return its edits oldest first, or None if there is no group. Close the open group.
        """
        self._open = False
        if not self._undo:
            return None
        group = self._undo.pop()
        self._redo.append(group)
        return list(group)

    def redo_group(self) -> list[Edit] | None:
        """Move the latest redo group back to the undo stack.

        Return its edits oldest first, or None if there is none. Close the open group.
        """
        self._open = False
        if not self._redo:
            return None
        group = self._redo.pop()
        self._undo.append(group)
        return list(group)
