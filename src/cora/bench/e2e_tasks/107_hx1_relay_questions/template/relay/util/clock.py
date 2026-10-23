"""Time helpers. Every function takes the current time as a parameter.

Passing the time in keeps the logic deterministic in tests. ``utc_iso`` is the only
function that reads the real clock, and only when called without arguments.
"""

import datetime


def utc_iso(now=None):
    """Return ``now`` (or the current UTC time) as an ISO 8601 string with Z suffix."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_expired(created_at, ttl_s, now):
    """Return True when ``now`` is at least ``ttl_s`` seconds after ``created_at``."""
    return (now - created_at) >= ttl_s
