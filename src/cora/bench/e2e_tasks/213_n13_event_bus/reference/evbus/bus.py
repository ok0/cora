"""In-process publish and subscribe bus."""

from collections.abc import Callable

from .errors import DispatchError
from .history import History
from .topics import matches, validate_pattern, validate_topic


class Bus:
    def __init__(self, history: int = 0) -> None:
        """Keep the last history published events when history > 0."""
        self._history = History(history) if history > 0 else None
        self._subs: dict[int, tuple[str, Callable[[str, object], object], int, bool]] = {}
        self._next = 1

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
        validate_pattern(pattern)
        token = self._next
        self._next += 1
        self._subs[token] = (pattern, handler, priority, once)
        if replay and self._history is not None:
            for topic, payload in self._history.matching(pattern):
                if once:
                    self._subs.pop(token, None)
                handler(topic, payload)
                if once:
                    break
        return token

    def unsubscribe(self, token: int) -> bool:
        """Remove a subscription. Return False if the token is unknown or already removed."""
        return self._subs.pop(token, None) is not None

    def publish(self, topic: str, payload: object = None) -> int:
        """Deliver an event to matching handlers and return how many were called."""
        validate_topic(topic)
        if self._history is not None:
            self._history.record(topic, payload)
        snapshot = sorted(self._subs.items(), key=lambda kv: (-kv[1][2], kv[0]))
        errors: list[tuple[int, BaseException]] = []
        called = 0
        for token, (pattern, handler, _priority, once) in snapshot:
            if not matches(pattern, topic):
                continue
            if once:
                self._subs.pop(token, None)
            called += 1
            try:
                handler(topic, payload)
            except Exception as exc:
                errors.append((token, exc))
        if errors:
            raise DispatchError(errors)
        return called
