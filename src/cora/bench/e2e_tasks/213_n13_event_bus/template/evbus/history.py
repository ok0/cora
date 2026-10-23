"""Bounded event history."""


class History:
    def __init__(self, maxlen: int) -> None:
        """Keep the last maxlen events. Raise ValueError if maxlen < 0."""
        raise NotImplementedError

    def record(self, topic: str, payload: object) -> None:
        """Append an event and drop the oldest one beyond maxlen."""
        raise NotImplementedError

    def matching(self, pattern: str) -> list[tuple[str, object]]:
        """Return the recorded (topic, payload) pairs whose topic matches, oldest first."""
        raise NotImplementedError
