"""Spool directory that keeps one JSON file per message.

Files are written under a temporary name and renamed into place, so a reader never
sees a half-written message. The directory is created on first use.
"""

import json
import os


class Spool:
    """Write, read and remove spooled messages inside ``root``."""

    def __init__(self, root):
        self.root = root

    def _path(self, message_id):
        return os.path.join(self.root, f"{message_id}.json")

    def write(self, message_id, message):
        """Store ``message`` under ``message_id`` and return the final path."""
        os.makedirs(self.root, exist_ok=True)
        final = self._path(message_id)
        tmp = final + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(message, handle, sort_keys=True)
        os.replace(tmp, final)
        return final

    def read(self, message_id):
        """Return the stored message, or raise KeyError when it is absent."""
        path = self._path(message_id)
        if not os.path.isfile(path):
            raise KeyError(message_id)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def remove(self, message_id):
        """Delete the spooled file if it exists. Returns True when one was removed."""
        path = self._path(message_id)
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False

    def ids(self):
        """Return the sorted ids of all spooled messages."""
        if not os.path.isdir(self.root):
            return []
        names = [n[:-5] for n in os.listdir(self.root) if n.endswith(".json")]
        return sorted(names)
