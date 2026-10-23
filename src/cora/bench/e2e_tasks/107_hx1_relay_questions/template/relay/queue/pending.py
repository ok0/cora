"""Tracking of messages that are in flight or waiting for a retry.

A message is pending from the moment it is handed to the sender until it is
either acknowledged or given up on. The tracker keeps the attempt count for each
message so that the drain loop can report how many tries were spent.
"""


class PendingTracker:
    """Remember the attempt count of every message that has not finished."""

    def __init__(self):
        self._attempts = {}

    def __contains__(self, key):
        return key in self._attempts

    def __len__(self):
        return len(self._attempts)

    def start(self, key):
        """Mark ``key`` as pending with zero attempts recorded."""
        self._attempts.setdefault(key, 0)

    def record_attempt(self, key):
        """Count one more attempt for ``key`` and return the new total."""
        if key not in self._attempts:
            raise KeyError(key)
        self._attempts[key] += 1
        return self._attempts[key]

    def finish(self, key):
        """Stop tracking ``key`` and return how many attempts it used."""
        return self._attempts.pop(key, 0)

    def snapshot(self):
        """Return a copy of the attempt counts keyed by message id."""
        return dict(self._attempts)
