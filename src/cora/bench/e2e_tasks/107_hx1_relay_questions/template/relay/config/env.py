"""Mapping from setting names to environment variables.

A variable is read only when it is set to a non-blank value. Blank values are
treated as unset so that an empty export does not shadow the defaults. Settings
that are not listed here can only come from the settings file.
"""

ENV_OVERRIDES = {
    "spool_dir": "RELAY_SPOOL_DIR",
    "max_retries": "RELAY_MAX_RETRIES",
    "backoff_base_s": "RELAY_BACKOFF_BASE_S",
    "backoff_cap_s": "RELAY_BACKOFF_CAP_S",
    "batch_size": "RELAY_BATCH_SIZE",
    "listen_port": "RELAY_LISTEN_PORT",
    "log_level": "RELAY_LOG_LEVEL",
}


def env_name(setting):
    """Return the environment variable that overrides ``setting``, or None."""
    return ENV_OVERRIDES.get(setting)


def env_value(setting, environ):
    """Return the raw override for ``setting`` from ``environ``, or None.

    ``environ`` is any mapping of variable names to strings, usually ``os.environ``.
    """
    var = ENV_OVERRIDES.get(setting)
    if var is None:
        return None
    value = environ.get(var, "")
    if not value.strip():
        return None
    return value
