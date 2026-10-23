import re
from dataclasses import dataclass

_AMOUNT = re.compile(r"(-?)([0-9]+)(?:\.([0-9]{2}))?")


@dataclass(frozen=True)
class Entry:
    date: str
    account: str
    amount_cents: int
    memo: str = ""


def parse_amount(s: str) -> int:
    m = _AMOUNT.fullmatch(s)
    if m is None:
        raise ValueError(f"bad amount: {s!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int(frac or "0")
    return -cents if sign else cents
