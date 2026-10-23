"""Bounded event history."""

from collections import deque

from .topics import matches


class History:
    def __init__(self, maxlen: int) -> None:
        """Keep the last maxlen events. Raise ValueError if maxlen < 0."""
        if maxlen < 0:
            raise ValueError("maxlen must be >= 0")
        self._events: deque[tuple[str, object]] = deque(maxlen=maxlen)

    def record(self, topic: str, payload: object) -> None:
        """Append an event and drop the oldest one beyond maxlen."""
        self._events.append((topic, payload))

    def matching(self, pattern: str) -> list[tuple[str, object]]:
        """Return the recorded (topic, payload) pairs whose topic matches, oldest first."""
        return [(t, p) for t, p in self._events if matches(pattern, t)]
