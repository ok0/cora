"""Duration measurements for relay operations.

A timer records elapsed seconds for each named operation. The clock is injected so
that tests and the status view can use a fixed clock.
"""

import time


class Timers:
    """Collect the durations of named operations."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._totals = {}
        self._counts = {}

    def record(self, name, seconds):
        """Add one measurement of ``seconds`` for ``name``."""
        if seconds < 0:
            raise ValueError("durations cannot be negative")
        self._totals[name] = self._totals.get(name, 0.0) + seconds
        self._counts[name] = self._counts.get(name, 0) + 1

    def elapsed(self, name, func, *args, **kwargs):
        """Call ``func`` and record how long it took under ``name``."""
        start = self._clock()
        try:
            return func(*args, **kwargs)
        finally:
            self.record(name, self._clock() - start)

    def mean(self, name):
        """Return the mean duration for ``name``, or 0.0 when nothing was recorded."""
        count = self._counts.get(name, 0)
        if count == 0:
            return 0.0
        return self._totals[name] / count
