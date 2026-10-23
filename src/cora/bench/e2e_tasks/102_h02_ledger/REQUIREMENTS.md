# Ledger balances and reports

Finish the `ledger` package in this directory. Some functions are stubs that raise
`NotImplementedError`; implement them. `tests/test_ledger.py` is the specification; do not modify it.
Keep `ledger/models.py`, `Book.add` and `Book.entries` as they are.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.

## Amounts

`parse_amount(s)` (already implemented in `ledger/models.py`) turns text into cents. Accepted forms:
an optional `-`, one or more digits, and optionally `.` followed by exactly two digits.
Anything else raises `ValueError(f"bad amount: {s!r}")`. Examples: `"12.30"` is 1230, `"-0.05"` is -5,
`"7"` is 700.

## Book (`ledger/book.py`)

- `balance(account) -> int`: the sum of `amount_cents` of the entries of that account; 0 if the
  account has no entries.
- `balances() -> dict[str, int]`: one key per account that has at least one entry, mapped to its
  balance. The keys are in sorted order. An empty book gives `{}`.

## Reports (`ledger/report.py`)

- `format_cents(n: int) -> str`: a minus sign for negative values, the absolute value with
  thousands separators `,` in the integer part, and exactly two decimals. Examples: `-1230` gives
  `"-12.30"`, `5` gives `"0.05"`, `123456` gives `"1,234.56"`, `0` gives `"0.00"`.
- `monthly_summary(book, account) -> list[tuple[str, int]]`: one `(month, total)` tuple per month in
  which the account has entries, where `month` is the first 7 characters of the entry date
  (`"YYYY-MM"`) and `total` is the sum of that account's `amount_cents` in that month. Only that
  account's entries count. The list is sorted by month. Months without entries are not listed.

## Import (`ledger/importer.py`)

`load_lines(lines: list[str]) -> Book` builds a `Book` from text lines:

- Each line is stripped of surrounding whitespace first.
- An empty line, or a line starting with `#`, is skipped.
- Any other line has the form `YYYY-MM-DD;account;amount;memo`. Split it on `;`; it must give exactly
  4 fields. The memo may be empty. The amount is converted with `parse_amount`; its `ValueError`
  is not caught.
- A line with another number of fields raises `ValueError("line N: expected 4 fields")`, where N is
  the 1-based position of the line in `lines` (skipped lines are counted).
- Entries are added to the book in input order.
