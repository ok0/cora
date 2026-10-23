"""In-process publish and subscribe bus."""

from collections.abc import Callable


class Bus:
    def __init__(self, history: int = 0) -> None:
        """Keep the last history published events when history > 0."""
        raise NotImplementedError

    def subscribe(
        self,
        pattern: str,
        handler: Callable[[str, object], object],
        *,
        priority: int = 0,
        once: bool = False,
        replay: bool = False,
    ) -> int:
        """Register a handler and return its token."""
        raise NotImplementedError

    def unsubscribe(self, token: int) -> bool:
        """Remove a subscription. Return False if the token is unknown or already removed."""
        raise NotImplementedError

    def publish(self, topic: str, payload: object = None) -> int:
        """Deliver an event to matching handlers and return how many were called."""
        raise NotImplementedError
