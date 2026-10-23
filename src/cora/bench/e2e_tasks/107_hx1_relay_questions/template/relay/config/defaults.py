"""Default settings for the relay.

Every value in this module is used when neither the settings file nor the
environment overrides it. The values are module constants and are never changed
at run time. ``DEFAULTS`` maps the public setting names to these values.
"""

MAX_RETRIES = 4
BACKOFF_BASE_S = 1.5
BACKOFF_CAP_S = 20.0
SPOOL_DIR = "/var/spool/relay"
BATCH_SIZE = 50
REQUEST_TIMEOUT_S = 10.0
LISTEN_PORT = 8025
LOG_LEVEL = "info"

DEFAULTS = {
    "max_retries": MAX_RETRIES,
    "backoff_base_s": BACKOFF_BASE_S,
    "backoff_cap_s": BACKOFF_CAP_S,
    "spool_dir": SPOOL_DIR,
    "batch_size": BATCH_SIZE,
    "request_timeout_s": REQUEST_TIMEOUT_S,
    "listen_port": LISTEN_PORT,
    "log_level": LOG_LEVEL,
}
