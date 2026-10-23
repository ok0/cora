"""Entry point for the command line tool.

``main`` parses the arguments, loads settings and dispatches to a command. It
returns the process exit code instead of calling ``sys.exit`` so that it can be
tested in-process.
"""

import sys

from relay.cli import commands
from relay.config.loader import load_settings

USAGE = "usage: relay <status|show ID|queue> [--settings PATH]"


def parse_args(argv):
    """Return ``(command, args, settings_path)`` or raise ValueError."""
    settings_path = None
    rest = []
    it = iter(argv)
    for item in it:
        if item == "--settings":
            settings_path = next(it, None)
            if settings_path is None:
                raise ValueError("--settings needs a path")
        else:
            rest.append(item)
    if not rest:
        raise ValueError("missing command")
    return rest[0], rest[1:], settings_path


def main(argv=None):
    """Run the command line tool and return an exit code."""
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        command, args, settings_path = parse_args(argv)
    except ValueError as err:
        print(f"{USAGE}\nerror: {err}", file=sys.stderr)
        return 2
    settings = load_settings(settings_path)
    return commands.dispatch(command, args, settings)
