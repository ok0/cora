"""Token bucket."""

import time


class TokenBucket:
    """Token bucket that starts full and refills continuously."""

    def __init__(self, capacity: int, refill_per_s: float, clock=time.monotonic):
        """Create a full bucket. Raise ValueError if capacity or refill_per_s is <= 0."""
        raise NotImplementedError

    @property
    def tokens(self) -> float:
        """Current token count after refill."""
        raise NotImplementedError

    def allow(self, cost: int = 1) -> bool:
        """Consume cost tokens and return True if available, else return False."""
        raise NotImplementedError

    def wait_time(self, cost: int = 1) -> float:
        """Seconds until cost tokens are available. 0.0 if they already are."""
        raise NotImplementedError
