"""In-process sender used by the relay and by the test bench.

The sender never opens sockets. ``Sender`` wraps a transport callable that does the
real work and retries failed calls according to the retry arithmetic and the
retry decision. A pause is taken through the optional ``sleep`` callable, so tests
can pass a recorder instead of waiting.
"""

from relay.transport import policy, retry


class Sender:
    """Deliver messages through ``transport`` with retries."""

    def __init__(self, transport, settings, sleep=None):
        self._transport = transport
        self._settings = settings
        self._sleep = sleep
        self.delivered = 0

    def send(self, message):
        """Deliver ``message`` and return the number of attempts that were used.

        The last error is re-raised when the attempts run out or the error is not
        transient.
        """
        total = retry.attempts(self._settings)
        last_error = None
        for attempt in range(1, total + 1):
            if attempt >= 2 and self._sleep is not None:
                self._sleep(retry.delay_before(attempt))
            try:
                self._transport(message)
            except Exception as err:  # noqa: BLE001
                last_error = err
                if not policy.is_transient_failure(err):
                    raise
                continue
            self.delivered += 1
            return attempt
        raise last_error

    def send_all(self, messages):
        """Deliver each message in order and return the list of attempt counts."""
        return [self.send(message) for message in messages]
