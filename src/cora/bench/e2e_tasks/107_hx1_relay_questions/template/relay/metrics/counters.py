"""Named counters for relay events such as deliveries and failures.

Counters only go up. ``snapshot`` returns a copy so callers cannot change the
values by accident.
"""


class Counters:
    """A set of named integer counters."""

    def __init__(self):
        self._values = {}

    def incr(self, name, by=1):
        """Add ``by`` to the counter ``name`` and return the new value."""
        if by < 0:
            raise ValueError("counters only increase")
        self._values[name] = self._values.get(name, 0) + by
        return self._values[name]

    def get(self, name):
        """Return the value of ``name``, or 0 when it was never incremented."""
        return self._values.get(name, 0)

    def snapshot(self):
        """Return a copy of all counters sorted by name."""
        return {k: self._values[k] for k in sorted(self._values)}
