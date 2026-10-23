"""Token bucket."""

import time


class TokenBucket:
    """Token bucket that starts full and refills continuously."""

    def __init__(self, capacity: int, refill_per_s: float, clock=time.monotonic):
        """Create a full bucket. Raise ValueError if capacity or refill_per_s is <= 0."""
        if capacity <= 0 or refill_per_s <= 0:
            raise ValueError("capacity and refill_per_s must be > 0")
        self.capacity = capacity
        self.refill_per_s = refill_per_s
        self.clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def _refill(self) -> None:
        now = self.clock()
        dt = now - self._last
        if dt > 0:
            self._tokens = min(self.capacity, self._tokens + dt * self.refill_per_s)
        self._last = now

    def _check_cost(self, cost: int) -> None:
        if cost <= 0 or cost > self.capacity:
            raise ValueError(f"cost must be in 1..{self.capacity}")

    @property
    def tokens(self) -> float:
        """Current token count after refill."""
        self._refill()
        return self._tokens

    def allow(self, cost: int = 1) -> bool:
        """Consume cost tokens and return True if available, else return False."""
        self._check_cost(cost)
        self._refill()
        if self._tokens >= cost:
            self._tokens -= cost
            return True
        return False

    def wait_time(self, cost: int = 1) -> float:
        """Seconds until cost tokens are available. 0.0 if they already are."""
        self._check_cost(cost)
        self._refill()
        if self._tokens >= cost:
            return 0.0
        return (cost - self._tokens) / self.refill_per_s
