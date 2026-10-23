"""Retry arithmetic for outgoing deliveries.

``attempts`` counts the first try plus every retry. With the default settings the
relay therefore makes ``1 + MAX_RETRIES`` deliveries for one message.

``delay_before`` gives the pause that is taken before a given attempt. The first
attempt has no pause. Each later attempt doubles the previous pause, starting at
``BACKOFF_BASE_S``, and the pause never exceeds ``BACKOFF_CAP_S``.

This module only computes numbers. Deciding whether a failure is retried at all is
done by ``relay.transport.policy``.
"""

from relay.config.defaults import BACKOFF_BASE_S, BACKOFF_CAP_S


def attempts(settings):
    """Return the total number of delivery attempts allowed by ``settings``."""
    return 1 + settings.max_retries


def delay_before(attempt):
    """Return the pause in seconds before ``attempt`` (1-based).

    Attempt 1 has no pause and is rejected here so callers cannot wait by mistake.
    """
    if attempt < 2:
        raise ValueError("the first attempt has no delay")
    return min(BACKOFF_BASE_S * 2 ** (attempt - 2), BACKOFF_CAP_S)


def schedule(settings):
    """Return the list of pauses for every retry allowed by ``settings``."""
    return [delay_before(n) for n in range(2, attempts(settings) + 1)]
