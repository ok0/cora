from .models import Entry


class Book:
    def __init__(self) -> None:
        self._entries: list[Entry] = []

    def add(self, entry: Entry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[Entry]:
        return list(self._entries)

    def balance(self, account: str) -> int:
        return sum(e.amount_cents for e in self._entries if e.account == account)

    def balances(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for e in self._entries:
            totals[e.account] = totals.get(e.account, 0) + e.amount_cents
        return {account: totals[account] for account in sorted(totals)}
