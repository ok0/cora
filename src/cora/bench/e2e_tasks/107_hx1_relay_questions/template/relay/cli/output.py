"""Output helpers for the command line tool.

Normal output goes to standard output and errors go to standard error. JSON is
always written with sorted keys so that the output is stable between runs.
"""

import json
import sys


def line(text):
    """Write one line of normal output."""
    sys.stdout.write(f"{text}\n")


def error(text):
    """Write one line of error output."""
    sys.stderr.write(f"error: {text}\n")


def as_json(value):
    """Return ``value`` as compact JSON text with sorted keys."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
