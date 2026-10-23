"""Injectable clocks for tests."""


class FakeClock:
    """A clock that only moves when advance is called."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt
