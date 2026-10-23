from .models import Entry


class Book:
    def __init__(self) -> None:
        self._entries: list[Entry] = []

    def add(self, entry: Entry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[Entry]:
        return list(self._entries)

    def balance(self, account: str) -> int:
        raise NotImplementedError

    def balances(self) -> dict[str, int]:
        raise NotImplementedError
