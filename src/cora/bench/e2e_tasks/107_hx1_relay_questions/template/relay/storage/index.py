"""In-memory index from message ids to their spool paths.

The index is rebuilt from the spool directory at start-up. It answers lookups
without touching the disk for every request.
"""


class MessageIndex:
    """Map message ids to spool paths and keep insertion order."""

    def __init__(self):
        self._paths = {}

    def __len__(self):
        return len(self._paths)

    def __contains__(self, message_id):
        return message_id in self._paths

    def add(self, message_id, path):
        """Record where ``message_id`` lives on disk."""
        self._paths[message_id] = path

    def path_for(self, message_id):
        """Return the spool path for ``message_id``, or None when unknown."""
        return self._paths.get(message_id)

    def discard(self, message_id):
        """Forget ``message_id``. Missing ids are ignored."""
        self._paths.pop(message_id, None)

    def ids(self):
        """Return the ids in the order they were added."""
        return list(self._paths)
