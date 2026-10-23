"""In-memory cart sessions keyed by session id."""

SESSIONS: dict = {}


def open_session(session_id: str) -> list:
    """Return the cart of a session, creating an empty cart when needed."""
    return SESSIONS.setdefault(session_id, [])


def close_session(session_id: str) -> None:
    """Forget the cart of a session. Closing an unknown session does nothing."""
    SESSIONS.pop(session_id, None)
