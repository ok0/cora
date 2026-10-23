"""Error types raised by the API layer and their HTTP status codes.

Every error the API can return is listed in ``STATUS_BY_ERROR``. Handlers raise
these types and never choose a status code themselves. Errors that are not listed
map to 500 through ``status_for``.
"""


class RelayError(Exception):
    """Base class for errors that the API maps to HTTP statuses."""

    transient = False


class MessageNotFound(RelayError):
    """The message id is not in the store."""


class InvalidMessage(RelayError):
    """The request body failed validation."""


class Conflict(RelayError):
    """The message is in a state that forbids the requested change."""


class Unavailable(RelayError):
    """The spool or a downstream service is temporarily unavailable."""

    transient = True


STATUS_BY_ERROR = {
    MessageNotFound: 410,
    InvalidMessage: 400,
    Conflict: 409,
    Unavailable: 503,
}

UNKNOWN_STATUS = 500


def status_for(err):
    """Return the HTTP status for ``err``, or 500 when the type is not listed."""
    for cls, code in STATUS_BY_ERROR.items():
        if isinstance(err, cls):
            return code
    return UNKNOWN_STATUS
