"""Per-key token buckets with idle eviction."""

import time


class KeyedLimiter:
    """One token bucket per key, dropped after an idle period."""

    def __init__(self, capacity: int, refill_per_s: float, idle_ttl_s: float, clock=time.monotonic):
        """Store the bucket settings. No buckets exist yet."""
        raise NotImplementedError

    def allow(self, key: str, cost: int = 1) -> bool:
        """Apply the key's bucket to a request of cost tokens."""
        raise NotImplementedError

    def active_keys(self) -> list[str]:
        """Sorted list of keys that still hold a bucket."""
        raise NotImplementedError
