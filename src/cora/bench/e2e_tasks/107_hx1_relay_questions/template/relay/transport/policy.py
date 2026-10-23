"""Decide whether a failed delivery is worth another attempt.

This is the only place where the retry decision is made. The sender asks
``is_transient_failure`` after every failed attempt and stops when the answer is
False. Errors are transient when they are network level timeouts or connection
problems, or when the error type sets ``transient = True``.

Errors that are not transient fail the delivery immediately, whatever the retry
settings say.
"""

PERMANENT_TYPES = (ValueError, KeyError, LookupError)
NETWORK_TYPES = (TimeoutError, ConnectionError)


def is_transient_failure(err):
    """Return True when a delivery that failed with ``err`` should be retried."""
    if isinstance(err, PERMANENT_TYPES):
        return False
    if isinstance(err, NETWORK_TYPES):
        return True
    return bool(getattr(err, "transient", False))
