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
        raise NotImplementedError

    def push(self, edit: Edit, join: bool) -> None:
        """Record an edit.

        With join=True and an open group, append to it; otherwise start a new open group.
        Clear redo and drop the oldest groups beyond max_groups.
        """
        raise NotImplementedError

    def last(self) -> Edit | None:
        """Return the last edit of the open group, or None if no group is open."""
        raise NotImplementedError

    def undo_group(self) -> list[Edit] | None:
        """Move the latest group to the redo stack.

        Return its edits oldest first, or None if there is no group. Close the open group.
        """
        raise NotImplementedError

    def redo_group(self) -> list[Edit] | None:
        """Move the latest redo group back to the undo stack.

        Return its edits oldest first, or None if there is none. Close the open group.
        """
        raise NotImplementedError
