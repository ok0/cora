"""Password hashing and login checks using only the standard library."""

import hashlib
import hmac


def hash_password(password: str, salt: str) -> str:
    """Return the hex SHA-256 digest of the salt followed by the password."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def verify_password(password: str, salt: str, digest: str) -> bool:
    """Return True when the password matches the stored digest."""
    return hmac.compare_digest(hash_password(password, salt), digest)
