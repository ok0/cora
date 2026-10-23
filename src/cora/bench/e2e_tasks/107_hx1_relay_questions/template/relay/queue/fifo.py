"""A first-in, first-out queue of messages waiting for delivery.

The queue keeps insertion order. ``pop_batch`` returns at most ``size`` messages
and never blocks, so the drain loop can decide when to stop.
"""

from collections import deque


class FifoQueue:
    """Bounded FIFO queue. ``capacity`` of None means unbounded."""

    def __init__(self, capacity=None):
        self._items = deque()
        self._capacity = capacity

    def __len__(self):
        return len(self._items)

    def push(self, message):
        """Append ``message``. Raises OverflowError when the queue is full."""
        if self._capacity is not None and len(self._items) >= self._capacity:
            raise OverflowError("queue is full")
        self._items.append(message)

    def pop(self):
        """Remove and return the oldest message, or None when empty."""
        if not self._items:
            return None
        return self._items.popleft()

    def pop_batch(self, size):
        """Remove and return up to ``size`` of the oldest messages."""
        out = []
        while self._items and len(out) < size:
            out.append(self._items.popleft())
        return out
