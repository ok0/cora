"""User account records."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    """A customer account. Inactive accounts cannot place orders."""

    user_id: int
    email: str
    active: bool = True


def normalise_email(email: str) -> str:
    """Return the email address stripped of spaces and in lower case."""
    return email.strip().lower()
