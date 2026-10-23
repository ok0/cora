"""Per-key token buckets with idle eviction."""

import time

from throttle.bucket import TokenBucket


class KeyedLimiter:
    """One token bucket per key, dropped after an idle period."""

    def __init__(self, capacity: int, refill_per_s: float, idle_ttl_s: float, clock=time.monotonic):
        """Store the bucket settings. No buckets exist yet."""
        self.capacity = capacity
        self.refill_per_s = refill_per_s
        self.idle_ttl_s = idle_ttl_s
        self.clock = clock
        self._buckets: dict[str, TokenBucket] = {}
        self._last: dict[str, float] = {}

    def _evict(self) -> None:
        now = self.clock()
        for key in [k for k, t in self._last.items() if now - t >= self.idle_ttl_s]:
            del self._buckets[key]
            del self._last[key]

    def allow(self, key: str, cost: int = 1) -> bool:
        """Apply the key's bucket to a request of cost tokens."""
        self._evict()
        now = self.clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_s, clock=self.clock)
            self._buckets[key] = bucket
        self._last[key] = now
        return bucket.allow(cost)

    def active_keys(self) -> list[str]:
        """Sorted list of keys that still hold a bucket."""
        self._evict()
        return sorted(self._buckets)
