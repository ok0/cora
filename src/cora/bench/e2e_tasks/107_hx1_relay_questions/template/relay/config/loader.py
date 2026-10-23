"""Build the effective settings from defaults, an optional file and the environment.

The order of precedence is: defaults, then the JSON settings file when it exists,
then environment overrides. Unknown keys in the settings file are an error so that
typos do not pass silently.
"""

import json
import os
from dataclasses import dataclass, fields

from relay.config.defaults import (
    BACKOFF_BASE_S,
    BACKOFF_CAP_S,
    BATCH_SIZE,
    LISTEN_PORT,
    LOG_LEVEL,
    MAX_RETRIES,
    REQUEST_TIMEOUT_S,
    SPOOL_DIR,
)
from relay.config.env import env_value

_CASTS = {
    "max_retries": int,
    "backoff_base_s": float,
    "backoff_cap_s": float,
    "spool_dir": str,
    "batch_size": int,
    "listen_port": int,
    "log_level": str,
}


@dataclass(frozen=True)
class Settings:
    """The effective settings. Instances are immutable once built."""

    max_retries: int = MAX_RETRIES
    backoff_base_s: float = BACKOFF_BASE_S
    backoff_cap_s: float = BACKOFF_CAP_S
    spool_dir: str = SPOOL_DIR
    batch_size: int = BATCH_SIZE
    request_timeout_s: float = REQUEST_TIMEOUT_S
    listen_port: int = LISTEN_PORT
    log_level: str = LOG_LEVEL


def load_settings(path=None, environ=None):
    """Return the effective settings.

    ``path`` is an optional JSON object file. ``environ`` defaults to ``os.environ``.
    """
    overrides = {}
    if path is not None and os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            overrides.update(json.load(handle))
    env = os.environ if environ is None else environ
    for name, cast in _CASTS.items():
        raw = env_value(name, env)
        if raw is not None:
            overrides[name] = cast(raw)
    known = {f.name for f in fields(Settings)}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(unknown)}")
    return Settings(**overrides)
