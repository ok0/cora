"""Command implementations for the relay command line tool.

Each command receives its arguments and the effective settings and returns an
exit code. Output goes through ``relay.cli.output`` so the format is the same for
every command.
"""

from relay.cli import output
from relay.queue.fifo import FifoQueue
from relay.storage.spool import Spool


def cmd_status(args, settings):
    """Print the spool location and the number of spooled messages."""
    spool = Spool(settings.spool_dir)
    output.line(f"spool: {settings.spool_dir}")
    output.line(f"messages: {len(spool.ids())}")
    return 0


def cmd_show(args, settings):
    """Print one spooled message by id. Returns 1 when the id is unknown."""
    if len(args) != 1:
        output.error("show needs exactly one message id")
        return 2
    spool = Spool(settings.spool_dir)
    try:
        message = spool.read(args[0])
    except KeyError:
        output.error(f"unknown message: {args[0]}")
        return 1
    output.line(output.as_json(message))
    return 0


def cmd_queue(args, settings):
    """Print the ids that are waiting, in spool order."""
    spool = Spool(settings.spool_dir)
    queue = FifoQueue()
    for message_id in spool.ids():
        queue.push(message_id)
    output.line(f"queued: {len(queue)}")
    return 0


COMMANDS = {
    "status": cmd_status,
    "show": cmd_show,
    "queue": cmd_queue,
}


def dispatch(name, args, settings):
    """Run the command called ``name``. Unknown names return exit code 2."""
    func = COMMANDS.get(name)
    if func is None:
        output.error(f"unknown command: {name}")
        return 2
    return func(args, settings)
