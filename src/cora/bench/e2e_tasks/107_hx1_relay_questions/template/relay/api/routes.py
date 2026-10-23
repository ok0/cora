"""URL routing table for the HTTP API.

Patterns use ``<name>`` for a path parameter. A route matches only when the method
is equal and every path segment matches. The first matching route wins.
"""

from relay.api import handlers

ROUTES = (
    ("GET", "/messages", handlers.list_messages),
    ("GET", "/messages/<message_id>", handlers.get_message),
)


def _segments(path):
    return [part for part in path.split("/") if part]


def match(method, path):
    """Return ``(handler, params)`` for the request, or ``(None, {})``."""
    parts = _segments(path)
    for route_method, pattern, handler in ROUTES:
        if route_method != method:
            continue
        pat = _segments(pattern)
        if len(pat) != len(parts):
            continue
        params = {}
        for want, got in zip(pat, parts):
            if want.startswith("<") and want.endswith(">"):
                params[want[1:-1]] = got
            elif want != got:
                break
        else:
            return handler, params
    return None, {}
