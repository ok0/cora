"""Request handlers for the HTTP API.

A handler takes the store and the parts of the request it needs and returns a
``(status, body)`` pair on success. Failures are raised as errors from
``relay.api.errors`` and turned into responses by ``handle_error``.
"""

from relay.api.errors import InvalidMessage, MessageNotFound, status_for


def get_message(store, message_id):
    """Return ``(200, message)`` for a known id, otherwise raise MessageNotFound."""
    if not isinstance(message_id, str) or not message_id:
        raise InvalidMessage("message id must be a non-empty string")
    try:
        message = store[message_id]
    except KeyError:
        raise MessageNotFound(message_id) from None
    return 200, message


def list_messages(store, limit=50):
    """Return ``(200, [...])`` with at most ``limit`` messages in store order."""
    if limit < 1:
        raise InvalidMessage("limit must be at least 1")
    items = list(store.values())[:limit]
    return 200, items


def handle_error(err):
    """Turn an error into ``(status, body)`` for the response."""
    body = {"error": type(err).__name__, "detail": str(err)}
    return status_for(err), body
